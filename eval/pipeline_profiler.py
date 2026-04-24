from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

STAGE_NAMES = {
    "S1": "PDF解析",
    "S2": "文档分块",
    "S3": "向量嵌入生成",
    "S4": "向量索引构建",
    "S5": "测试集生成",
    "S6": "检索匹配",
    "S7": "答案生成",
    "S8": "报告整合",
}


@dataclass
class StageMetrics:
    stage_id: str
    stage_name: str
    start_time: float = 0.0
    end_time: float = 0.0
    duration_seconds: float = 0.0
    cpu_percent_avg: float = 0.0
    cpu_percent_peak: float = 0.0
    memory_mb_avg: float = 0.0
    memory_mb_peak: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    call_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_duration(self, seconds: float) -> None:
        self.duration_seconds += seconds
        self.call_count += 1

    def add_token_usage(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

    def merge_resource_stats(
        self,
        cpu_avg: float,
        cpu_peak: float,
        mem_avg: float,
        mem_peak: float,
    ) -> None:
        if self.call_count <= 1:
            self.cpu_percent_avg = cpu_avg
            self.cpu_percent_peak = cpu_peak
            self.memory_mb_avg = mem_avg
            self.memory_mb_peak = mem_peak
        else:
            total_cpu = self.cpu_percent_avg * (self.call_count - 1) + cpu_avg
            self.cpu_percent_avg = total_cpu / self.call_count
            self.cpu_percent_peak = max(self.cpu_percent_peak, cpu_peak)
            total_mem = self.memory_mb_avg * (self.call_count - 1) + mem_avg
            self.memory_mb_avg = total_mem / self.call_count
            self.memory_mb_peak = max(self.memory_mb_peak, mem_peak)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "stage_name": self.stage_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": round(self.duration_seconds, 4),
            "call_count": self.call_count,
            "cpu_percent_avg": round(self.cpu_percent_avg, 2),
            "cpu_percent_peak": round(self.cpu_percent_peak, 2),
            "memory_mb_avg": round(self.memory_mb_avg, 2),
            "memory_mb_peak": round(self.memory_mb_peak, 2),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "metadata": self.metadata,
        }


@dataclass
class ResourceSample:
    timestamp: float
    cpu_percent: float
    memory_mb: float


class ResourceMonitor:
    def __init__(self, interval: float = 0.5):
        self.interval = interval
        self._samples: list[ResourceSample] = []
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

        try:
            import psutil

            self._psutil = psutil
            self._process = psutil.Process(os.getpid())
            self._available = True
        except ImportError:
            logger.warning(
                "psutil not available, resource monitoring disabled. "
                "Install with: pip install psutil"
            )
            self._psutil = None
            self._process = None
            self._available = False

    def start(self) -> None:
        if not self._available:
            return

        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.debug("Resource monitor started")

    def stop(self) -> list[ResourceSample]:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        with self._lock:
            samples = self._samples.copy()
            self._samples.clear()

        logger.debug(f"Resource monitor stopped, collected {len(samples)} samples")
        return samples

    def _monitor_loop(self) -> None:
        while self._running:
            try:
                cpu = self._process.cpu_percent(interval=0)
                mem_info = self._process.memory_info()
                memory_mb = mem_info.rss / 1024 / 1024

                sample = ResourceSample(
                    timestamp=time.perf_counter(),
                    cpu_percent=cpu,
                    memory_mb=memory_mb,
                )

                with self._lock:
                    self._samples.append(sample)

                time.sleep(self.interval)
            except Exception as e:
                logger.warning(f"Resource monitoring error: {e}")
                time.sleep(self.interval)

    def get_current_stats(self) -> dict[str, float]:
        if not self._available:
            return {"cpu_percent": 0.0, "memory_mb": 0.0}

        try:
            cpu = self._process.cpu_percent(interval=0)
            mem_info = self._process.memory_info()
            memory_mb = mem_info.rss / 1024 / 1024
            return {"cpu_percent": cpu, "memory_mb": memory_mb}
        except Exception:
            return {"cpu_percent": 0.0, "memory_mb": 0.0}


class PipelineProfiler:
    def __init__(
        self,
        experiment_name: str = "unnamed",
        total_pages: int = 0,
        total_questions: int = 0,
        monitor_interval: float = 0.5,
    ):
        self.experiment_name = experiment_name
        self.total_pages = total_pages
        self.total_questions = total_questions
        self.start_time: float | None = None
        self.end_time: float | None = None

        self._stages: dict[str, StageMetrics] = {}
        self._current_stage_id: str | None = None
        self._stage_start_time: float | None = None

        self._resource_monitor = ResourceMonitor(interval=monitor_interval)

    def start_profiling(self) -> None:
        self.start_time = time.perf_counter()
        self._resource_monitor.start()
        logger.info(f"Pipeline profiling started for experiment: {self.experiment_name}")

    def stop_profiling(self) -> None:
        self.end_time = time.perf_counter()
        self._resource_monitor.stop()
        logger.info(
            f"Pipeline profiling stopped. Total duration: {self.get_total_duration():.2f}s"
        )

    @contextmanager
    def profile_stage(
        self,
        stage_id: str,
        metadata: dict[str, Any] | None = None,
    ):
        self.begin_stage(stage_id, metadata or {})
        try:
            yield
        finally:
            self.end_stage()

    def begin_stage(self, stage_id: str, metadata: dict[str, Any] | None = None) -> None:
        if self._current_stage_id is not None:
            logger.warning(
                f"Stage {self._current_stage_id} not ended before starting {stage_id}"
            )
            self.end_stage()

        self._current_stage_id = stage_id
        self._stage_start_time = time.perf_counter()

        stage_name = STAGE_NAMES.get(stage_id, stage_id)
        logger.debug(f"Stage {stage_id} ({stage_name}) started")

    def end_stage(self) -> StageMetrics:
        if self._current_stage_id is None:
            logger.warning("No stage to end")
            return StageMetrics(stage_id="UNKNOWN", stage_name="Unknown")

        stage_id = self._current_stage_id
        stage_end_time = time.perf_counter()
        duration = stage_end_time - (self._stage_start_time or stage_end_time)

        stage_name = STAGE_NAMES.get(stage_id, stage_id)

        current_stats = self._resource_monitor.get_current_stats()
        cpu_avg = current_stats["cpu_percent"]
        cpu_peak = cpu_avg
        mem_avg = current_stats["memory_mb"]
        mem_peak = mem_avg

        if stage_id in self._stages:
            existing = self._stages[stage_id]
            existing.add_duration(duration)
            existing.end_time = stage_end_time
            existing.merge_resource_stats(cpu_avg, cpu_peak, mem_avg, mem_peak)
            metrics = existing
        else:
            metrics = StageMetrics(
                stage_id=stage_id,
                stage_name=stage_name,
                start_time=self._stage_start_time or 0.0,
                end_time=stage_end_time,
                duration_seconds=duration,
                cpu_percent_avg=cpu_avg,
                cpu_percent_peak=cpu_peak,
                memory_mb_avg=mem_avg,
                memory_mb_peak=mem_peak,
                call_count=1,
            )
            self._stages[stage_id] = metrics

        logger.debug(
            f"Stage {stage_id} ({stage_name}) ended: {duration:.2f}s "
            f"(total: {metrics.duration_seconds:.2f}s, calls: {metrics.call_count})"
        )

        self._current_stage_id = None
        self._stage_start_time = None

        return metrics

    def report_stage_tokens(
        self, stage_id: str, input_tokens: int, output_tokens: int
    ) -> None:
        if stage_id not in self._stages:
            stage_name = STAGE_NAMES.get(stage_id, stage_id)
            self._stages[stage_id] = StageMetrics(
                stage_id=stage_id,
                stage_name=stage_name,
            )
        self._stages[stage_id].add_token_usage(input_tokens, output_tokens)

    def get_total_duration(self) -> float:
        if self.start_time is None:
            return 0.0
        end = self.end_time if self.end_time is not None else time.perf_counter()
        return end - self.start_time

    def get_stage_metrics(self, stage_id: str) -> StageMetrics | None:
        return self._stages.get(stage_id)

    def get_all_stage_metrics(self) -> dict[str, StageMetrics]:
        return self._stages.copy()

    def get_normalized_metrics(self) -> dict[str, Any]:
        total_duration = self.get_total_duration()

        doc_stages = ["S1", "S2", "S3", "S4"]
        doc_time = sum(
            self._stages[s].duration_seconds for s in doc_stages if s in self._stages
        )

        qa_stages = ["S6", "S7"]
        qa_time = sum(
            self._stages[s].duration_seconds for s in qa_stages if s in self._stages
        )

        per_page_time = doc_time / self.total_pages if self.total_pages > 0 else 0.0
        per_question_time = (
            qa_time / self.total_questions if self.total_questions > 0 else 0.0
        )

        return {
            "total_duration_seconds": round(total_duration, 2),
            "document_processing_time": round(doc_time, 2),
            "qa_processing_time": round(qa_time, 2),
            "per_page_time_seconds": round(per_page_time, 4),
            "per_question_time_seconds": round(per_question_time, 4),
            "total_pages": self.total_pages,
            "total_questions": self.total_questions,
        }

    def get_resource_summary(self) -> dict[str, Any]:
        if not self._stages:
            return {
                "cpu_percent_avg": 0.0,
                "cpu_percent_peak": 0.0,
                "memory_mb_avg": 0.0,
                "memory_mb_peak": 0.0,
            }

        all_cpu = [
            m.cpu_percent_avg for m in self._stages.values() if m.cpu_percent_avg > 0
        ]
        all_cpu_peak = [m.cpu_percent_peak for m in self._stages.values()]
        all_mem = [
            m.memory_mb_avg for m in self._stages.values() if m.memory_mb_avg > 0
        ]
        all_mem_peak = [m.memory_mb_peak for m in self._stages.values()]

        return {
            "cpu_percent_avg": (
                round(sum(all_cpu) / len(all_cpu), 2) if all_cpu else 0.0
            ),
            "cpu_percent_peak": (
                round(max(all_cpu_peak), 2) if all_cpu_peak else 0.0
            ),
            "memory_mb_avg": (
                round(sum(all_mem) / len(all_mem), 2) if all_mem else 0.0
            ),
            "memory_mb_peak": (
                round(max(all_mem_peak), 2) if all_mem_peak else 0.0
            ),
        }

    def get_token_summary(self) -> dict[str, Any]:
        total_input = sum(m.input_tokens for m in self._stages.values())
        total_output = sum(m.output_tokens for m in self._stages.values())

        by_stage = {}
        for stage_id, metrics in self._stages.items():
            if metrics.input_tokens > 0 or metrics.output_tokens > 0:
                by_stage[stage_id] = {
                    "stage_name": metrics.stage_name,
                    "input_tokens": metrics.input_tokens,
                    "output_tokens": metrics.output_tokens,
                    "total_tokens": metrics.input_tokens + metrics.output_tokens,
                }

        return {
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "by_stage": by_stage,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_name": self.experiment_name,
            "start_timestamp": datetime.fromtimestamp(self.start_time).isoformat()
            if self.start_time
            else None,
            "end_timestamp": datetime.fromtimestamp(self.end_time).isoformat()
            if self.end_time
            else None,
            "normalized": self.get_normalized_metrics(),
            "resource_summary": self.get_resource_summary(),
            "token_summary": self.get_token_summary(),
            "stages": {sid: m.to_dict() for sid, m in self._stages.items()},
        }

    def save_report(
        self,
        output_dir: Path,
        filename: str = "profile_data.json",
    ) -> Path:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / filename
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

        logger.success(f"Profile data saved to: {output_path}")
        return output_path

    def generate_markdown_report(self) -> str:
        lines = []
        lines.append("# Pipeline 性能评估报告")
        lines.append("")
        lines.append(f"**实验**: {self.experiment_name}")
        lines.append(f"**评估时间**: {datetime.now().isoformat()}")
        lines.append(f"**数据规模**: {self.total_pages} 页, {self.total_questions} 个问题")
        lines.append("")

        lines.append("## 1. 总体耗时概览")
        lines.append("")
        lines.append(
            "| 环节 | 名称 | 耗时(s) | 占比 | 调用次数 | CPU平均 | 内存峰值(MB) |"
        )
        lines.append(
            "|------|------|---------|------|---------|---------|-------------|"
        )

        total_duration = self.get_total_duration()
        for stage_id in sorted(self._stages.keys()):
            m = self._stages[stage_id]
            pct = (
                (m.duration_seconds / total_duration * 100) if total_duration > 0 else 0
            )
            lines.append(
                f"| {stage_id} | {m.stage_name} | {m.duration_seconds:.2f} | "
                f"{pct:.1f}% | {m.call_count} | {m.cpu_percent_avg:.1f}% | {m.memory_mb_peak:.1f} |"
            )

        lines.append(
            f"| **总计** | - | **{total_duration:.2f}** | **100%** | - | - | - |"
        )
        lines.append("")

        normalized = self.get_normalized_metrics()
        lines.append("## 2. 归一化分析")
        lines.append("")
        lines.append("### 2.1 文档处理归一化")
        lines.append(f"- 单页平均耗时: **{normalized['per_page_time_seconds']:.4f}s/页**")
        lines.append(f"- 文档处理总耗时: {normalized['document_processing_time']:.2f}s")
        lines.append("")

        lines.append("### 2.2 问答处理归一化")
        lines.append(
            f"- 单问题平均耗时: **{normalized['per_question_time_seconds']:.4f}s/问题**"
        )
        lines.append(f"- 问答处理总耗时: {normalized['qa_processing_time']:.2f}s")
        lines.append("")

        resource = self.get_resource_summary()
        lines.append("## 3. 资源消耗")
        lines.append("")
        lines.append("### 3.1 CPU 使用率")
        lines.append(f"- 平均使用率: {resource['cpu_percent_avg']:.1f}%")
        lines.append(f"- 峰值使用率: {resource['cpu_percent_peak']:.1f}%")
        lines.append("")

        lines.append("### 3.2 内存消耗")
        lines.append(f"- 平均内存: {resource['memory_mb_avg']:.1f}MB")
        lines.append(f"- 峰值内存: {resource['memory_mb_peak']:.1f}MB")
        lines.append("")

        token_summary = self.get_token_summary()
        lines.append("### 3.3 Token 消耗")
        lines.append("")
        lines.append("| 环节 | 输入Token | 输出Token | 总Token |")
        lines.append("|------|----------|----------|---------|")

        for stage_id, data in sorted(token_summary["by_stage"].items()):
            lines.append(
                f"| {stage_id} {data['stage_name']} | {data['input_tokens']:,} | "
                f"{data['output_tokens']:,} | {data['total_tokens']:,} |"
            )

        lines.append(
            f"| **总计** | **{token_summary['total_input_tokens']:,}** | "
            f"**{token_summary['total_output_tokens']:,}** | "
            f"**{token_summary['total_tokens']:,}** |"
        )
        lines.append("")

        lines.append("## 4. 性能瓶颈分析")
        lines.append("")
        if self._stages:
            bottleneck = max(self._stages.values(), key=lambda m: m.duration_seconds)
            lines.append(
                f"- 最耗时环节: **{bottleneck.stage_id} {bottleneck.stage_name}** ({bottleneck.duration_seconds:.2f}s)"
            )
            lines.append("")

        lines.append("## 5. 优化建议")
        lines.append("")
        lines.append("基于性能数据，建议关注以下优化方向：")
        lines.append("")

        suggestions = []
        if (
            "S1" in self._stages
            and self._stages["S1"].duration_seconds > total_duration * 0.3
        ):
            suggestions.append(
                "1. **PDF解析优化**: 考虑使用并行解析或更快的解析算法"
            )
        if (
            "S3" in self._stages
            and self._stages["S3"].duration_seconds > total_duration * 0.3
        ):
            suggestions.append(
                "1. **向量嵌入优化**: 考虑增大批处理大小或使用GPU加速"
            )
        if (
            "S7" in self._stages
            and self._stages["S7"].duration_seconds > total_duration * 0.3
        ):
            suggestions.append(
                "1. **答案生成优化**: 考虑使用更快的LLM或减少上下文长度"
            )
        if (
            "S6" in self._stages
            and self._stages["S6"].duration_seconds > total_duration * 0.3
        ):
            suggestions.append(
                "1. **检索优化**: 检索耗时偏高，检查向量索引规模和检索参数"
            )

        for i, s in enumerate(suggestions, 1):
            lines.append(f"{i}. {s[3:]}")

        lines.append("")
        lines.append("---")
        lines.append(f"*报告生成时间: {datetime.now().isoformat()}*")

        return "\n".join(lines)


def profile_stage(
    profiler: PipelineProfiler, stage_id: str, metadata: dict[str, Any] | None = None
):
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            with profiler.profile_stage(stage_id, metadata):
                return func(*args, **kwargs)

        return wrapper

    return decorator
