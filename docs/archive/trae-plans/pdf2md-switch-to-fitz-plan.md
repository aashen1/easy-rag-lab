# RAG系统PDF处理链路技术分析与优化建议

## 一、核心问题诊断

从你提供的chunk样本可以看出几个明显问题：

```
"**==> picture [102 x 21] intentionally omitted <==**"  ← 图片被丢弃
"请务必阅读末页声明。\n\n3\n\n"                          ← 页脚噪音混入正文
"start_token: 2048, end_token: 2560"                    ← 按token硬切，无语义边界
```

这说明当前流程的问题不是单点问题，而是**整条链路的设计缺陷**。

------

## 二、三个核心问题的专业分析

### 问题1：pymupdf4llm默认转换质量

**根本原因分析：**

`pymupdf4llm.to_markdown()` 底层仍调用 PyMuPDF（fitz），但它做了许多"对话式AI友好"的假设，这些假设在金融文档上会失效：

| 场景     | pymupdf4llm的处理              | 金融文档实际情况             |
| -------- | ------------------------------ | ---------------------------- |
| 多栏布局 | 按坐标顺序拼接，易乱序         | 研报普遍双栏排版             |
| 表格     | 转为MD表格，但复杂表格丢失结构 | 财务报表是核心内容           |
| 页眉页脚 | 不过滤，混入正文               | "请务必阅读末页声明"反复出现 |
| 图表     | `intentionally omitted`        | 关键的行情图、估值图         |
| 页码     | 可能保留为孤立数字行           | `3` 这种孤立数字噪音         |

**结论：默认参数不适合金融文档，但并非没有调优空间（见第三部分）。**

------

### 问题2：Chunk与页码关联

**对AI启发式提取页码方案的评估：**

你描述的"从MD中搜索`1/232`格式页码"策略存在以下风险：

```
风险1：页码格式不统一
  - "第3页"、"Page 3"、"3/232"、"- 3 -" 均可能出现
  
风险2：页码被切块边界分割
  - 页码文本"3"可能在chunk_003末尾，正文在chunk_004开头
  
风险3：扫描版PDF
  - 页码完全不存在于文本层

风险4：AI幻觉
  - 当页码信息模糊时，LLM可能"猜测"错误页码
```

**正确方案：在提取阶段就绑定页码**，这是元数据问题，不应交给LLM推断。

------

### 问题3：工具选择评估

```
pymupdf4llm  →  便利性高，控制力弱
PyMuPDF(fitz) →  控制力强，需自行实现布局分析
pdfplumber   →  表格提取最强，适合作为补强工具
```

**对于金融文档RAG，推荐分层策略**（详见下方）。

------

## 三、推荐技术路径

### 架构设计：三层处理流程

```
PDF
 │
 ├─[层1] 结构感知提取（fitz + pdfplumber）
 │        ├─ 文本块（带页码、坐标）
 │        ├─ 表格（pdfplumber专项处理）
 │        └─ 图片（base64存储或路径引用）
 │
 ├─[层2] 噪音过滤 + 布局重组
 │        ├─ 过滤页眉页脚
 │        ├─ 修复多栏乱序
 │        └─ 生成带元数据的结构化文档
 │
 └─[层3] 语义感知Chunking
          ├─ 按标题层级切块
          ├─ 每个chunk携带page_range
          └─ 输出标准化JSONL
```

------

### 核心代码实现

#### Layer 1：结构感知提取器

```python
import fitz  # PyMuPDF
import pdfplumber
import re
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class PageBlock:
    """页面内容块，携带完整位置元数据"""
    page_num: int          # 1-indexed
    block_type: str        # "text" | "table" | "image" | "header" | "footer"
    content: str
    bbox: tuple            # (x0, y0, x1, y1)
    font_size: float = 0.0
    is_bold: bool = False
    

class FinancialPDFExtractor:
    """
    金融文档专用PDF提取器
    策略：fitz处理文本/布局，pdfplumber专项处理表格
    """
    
    # 常见金融文档页眉页脚特征
    NOISE_PATTERNS = [
        r"请务必阅读.{0,20}声明",
        r"^\s*\d+\s*$",                    # 孤立页码数字
        r"^\s*\d+\s*/\s*\d+\s*$",          # "3/232"格式
        r"(?:内部资料|机密|仅供参考).{0,30}$",
        r"^(?:www\.|http).+$",             # URL
        r"证券研究报告",                    # 常见研报标题重复
    ]
    
    def __init__(self, pdf_path: str):
        self.pdf_path = Path(pdf_path)
        self.fitz_doc = fitz.open(str(pdf_path))
        self.total_pages = len(self.fitz_doc)
        self._noise_re = [re.compile(p) for p in self.NOISE_PATTERNS]
    
    def _is_noise(self, text: str, bbox: tuple, page_height: float) -> bool:
        """基于内容特征+位置判断是否为噪音块"""
        text_stripped = text.strip()
        
        # 位置过滤：页面顶部10%或底部10%的短文本
        y0, y1 = bbox[1], bbox[3]
        is_header_zone = y0 < page_height * 0.10
        is_footer_zone = y1 > page_height * 0.90
        
        if (is_header_zone or is_footer_zone) and len(text_stripped) < 80:
            return True
        
        # 内容模式过滤
        for pattern in self._noise_re:
            if pattern.search(text_stripped):
                return True
        
        return False
    
    def _detect_columns(self, page: fitz.Page) -> int:
        """检测页面栏数（单栏/双栏）"""
        page_width = page.rect.width
        blocks = page.get_text("blocks")
        
        if not blocks:
            return 1
            
        # 统计文本块的x中心点分布
        x_centers = [
            (b[0] + b[2]) / 2 
            for b in blocks 
            if b[6] == 0  # type 0 = text
        ]
        
        if not x_centers:
            return 1
        
        # 如果文本块中心点明显分为左右两群，判断为双栏
        left_count = sum(1 for x in x_centers if x < page_width * 0.5)
        right_count = len(x_centers) - left_count
        
        if left_count > 2 and right_count > 2:
            ratio = min(left_count, right_count) / max(left_count, right_count)
            if ratio > 0.3:
                return 2
        
        return 1
    
    def _extract_page_blocks(self, page_num: int) -> list[PageBlock]:
        """提取单页所有内容块，保留位置元数据"""
        page = self.fitz_doc[page_num - 1]
        page_height = page.rect.height
        page_width = page.rect.width
        column_count = self._detect_columns(page)
        
        blocks = []
        raw_blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        
        for block in raw_blocks:
            if block["type"] == 1:  # 图片块
                blocks.append(PageBlock(
                    page_num=page_num,
                    block_type="image",
                    content=f"[图片: 页{page_num}]",
                    bbox=tuple(block["bbox"]),
                ))
                continue
            
            if block["type"] != 0:  # 非文本非图片跳过
                continue
            
            # 提取文本块的字体信息（用于标题检测）
            full_text = ""
            max_font_size = 0.0
            is_bold = False
            
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    full_text += span["text"]
                    if span["size"] > max_font_size:
                        max_font_size = span["size"]
                    if "bold" in span.get("font", "").lower():
                        is_bold = True
                full_text += "\n"
            
            full_text = full_text.strip()
            if not full_text:
                continue
            
            bbox = tuple(block["bbox"])
            
            if self._is_noise(full_text, bbox, page_height):
                continue
            
            blocks.append(PageBlock(
                page_num=page_num,
                block_type="text",
                content=full_text,
                bbox=bbox,
                font_size=max_font_size,
                is_bold=is_bold,
            ))
        
        # 双栏文档：按左栏→右栏→y坐标排序
        if column_count == 2:
            mid_x = page_width / 2
            blocks.sort(key=lambda b: (
                0 if b.bbox[0] < mid_x else 1,  # 左栏优先
                b.bbox[1]                         # 再按y坐标
            ))
        else:
            blocks.sort(key=lambda b: b.bbox[1])
        
        return blocks
    
    def _extract_tables_with_pdfplumber(self, page_num: int) -> list[PageBlock]:
        """使用pdfplumber专项提取表格，转换为Markdown"""
        tables = []
        
        try:
            with pdfplumber.open(str(self.pdf_path)) as pdf:
                page = pdf.pages[page_num - 1]
                
                # pdfplumber表格提取设置（针对金融报表优化）
                table_settings = {
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "snap_tolerance": 3,
                    "join_tolerance": 3,
                    "edge_min_length": 10,
                }
                
                extracted = page.extract_tables(table_settings)
                
                for i, table_data in enumerate(extracted):
                    if not table_data or not table_data[0]:
                        continue
                    
                    md_table = self._table_to_markdown(table_data)
                    if not md_table:
                        continue
                    
                    # 获取表格的边界框
                    plumber_tables = page.find_tables(table_settings)
                    bbox = tuple(plumber_tables[i].bbox) if i < len(plumber_tables) else (0, 0, 0, 0)
                    
                    tables.append(PageBlock(
                        page_num=page_num,
                        block_type="table",
                        content=md_table,
                        bbox=bbox,
                    ))
        except Exception as e:
            # pdfplumber失败时静默降级，不影响主流程
            pass
        
        return tables
    
    def _table_to_markdown(self, table_data: list) -> str:
        """将pdfplumber表格数据转换为标准Markdown表格"""
        if not table_data:
            return ""
        
        # 清理None值
        cleaned = [
            [str(cell).strip() if cell is not None else "" for cell in row]
            for row in table_data
        ]
        
        if not cleaned[0]:
            return ""
        
        col_count = max(len(row) for row in cleaned)
        
        # 标准化行长度
        for row in cleaned:
            while len(row) < col_count:
                row.append("")
        
        lines = []
        # 表头
        lines.append("| " + " | ".join(cleaned[0]) + " |")
        lines.append("|" + "|".join(["---"] * col_count) + "|")
        # 数据行
        for row in cleaned[1:]:
            lines.append("| " + " | ".join(row) + " |")
        
        return "\n".join(lines)
    
    def extract_all(self) -> list[PageBlock]:
        """提取全文档所有内容块"""
        all_blocks = []
        
        for page_num in range(1, self.total_pages + 1):
            text_blocks = self._extract_page_blocks(page_num)
            table_blocks = self._extract_tables_with_pdfplumber(page_num)
            
            # 合并文本块和表格块，按y坐标排序（表格替换对应位置的文本）
            combined = self._merge_text_and_tables(text_blocks, table_blocks)
            all_blocks.extend(combined)
        
        return all_blocks
    
    def _merge_text_and_tables(
        self, 
        text_blocks: list[PageBlock], 
        table_blocks: list[PageBlock]
    ) -> list[PageBlock]:
        """合并文本块和表格块：表格区域的文本块用pdfplumber结果替换"""
        if not table_blocks:
            return text_blocks
        
        result = []
        for tb in text_blocks:
            # 检查文本块是否与某个表格bbox重叠
            overlaps_table = any(
                self._bbox_overlap(tb.bbox, tab.bbox) > 0.5
                for tab in table_blocks
            )
            if not overlaps_table:
                result.append(tb)
        
        result.extend(table_blocks)
        result.sort(key=lambda b: b.bbox[1])
        return result
    
    def _bbox_overlap(self, bbox1: tuple, bbox2: tuple) -> float:
        """计算两个bbox的重叠比例"""
        x0 = max(bbox1[0], bbox2[0])
        y0 = max(bbox1[1], bbox2[1])
        x1 = min(bbox1[2], bbox2[2])
        y1 = min(bbox1[3], bbox2[3])
        
        if x1 <= x0 or y1 <= y0:
            return 0.0
        
        overlap_area = (x1 - x0) * (y1 - y0)
        area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
        
        return overlap_area / area1 if area1 > 0 else 0.0
    
    def close(self):
        self.fitz_doc.close()
```

------

#### Layer 2：标题感知的语义Chunker

```python
from dataclasses import dataclass, field
from typing import Optional
import re
import json


@dataclass
class Chunk:
    chunk_id: str
    text: str
    metadata: dict = field(default_factory=dict)


class SemanticChunker:
    """
    语义感知切块器
    核心原则：按文档逻辑结构切块，而非按固定token数硬切
    """
    
    # 金融文档标题模式
    HEADING_PATTERNS = [
        (1, re.compile(r"^#{1}\s+.+")),           # MD一级标题
        (2, re.compile(r"^#{2}\s+.+")),           # MD二级标题  
        (3, re.compile(r"^#{3}\s+.+")),           # MD三级标题
        (2, re.compile(r"^[一二三四五六七八九十]+[、.．]\s*.+")),  # 中文数字标题
        (3, re.compile(r"^\d+[、.．]\s*.+")),     # 阿拉伯数字标题
        (4, re.compile(r"^（\d+）|^\(\d+\)")),   # 括号数字子标题
    ]
    
    def __init__(
        self, 
        max_tokens: int = 1024,
        overlap_tokens: int = 128,
        min_chunk_tokens: int = 50,
    ):
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.min_chunk_tokens = min_chunk_tokens
    
    def _estimate_tokens(self, text: str) -> int:
        """中英文混合token估算（粗略：中文1字≈1.5token，英文4字≈1token）"""
        chinese = len(re.findall(r'[\u4e00-\u9fff]', text))
        others = len(text) - chinese
        return int(chinese * 1.5 + others / 4)
    
    def _detect_heading_level(self, text: str) -> Optional[int]:
        """检测文本是否为标题，返回层级（1-4）或None"""
        for level, pattern in self.HEADING_PATTERNS:
            if pattern.match(text.strip()):
                return level
        return None
    
    def _blocks_to_sections(self, blocks: list[PageBlock]) -> list[dict]:
        """
        将PageBlocks按标题层级组织为树状章节结构
        每个section包含: title, level, blocks, page_range
        """
        sections = []
        current_section = {
            "title": "导言",
            "level": 0,
            "blocks": [],
            "start_page": blocks[0].page_num if blocks else 1,
            "end_page": blocks[0].page_num if blocks else 1,
        }
        
        for block in blocks:
            # 对于字体大小异常大的文本块，也检测为标题
            heading_level = self._detect_heading_level(block.content)
            
            # 使用字体大小辅助判断标题（金融文档标题通常>12pt）
            if heading_level is None and block.font_size > 12 and block.is_bold:
                if len(block.content) < 100:  # 标题通常较短
                    heading_level = 2
            
            if heading_level is not None:
                # 保存当前章节
                if current_section["blocks"]:
                    sections.append(current_section)
                
                # 开启新章节
                current_section = {
                    "title": block.content.strip(),
                    "level": heading_level,
                    "blocks": [block],
                    "start_page": block.page_num,
                    "end_page": block.page_num,
                }
            else:
                current_section["blocks"].append(block)
                current_section["end_page"] = block.page_num
        
        if current_section["blocks"]:
            sections.append(current_section)
        
        return sections
    
    def chunk(
        self, 
        blocks: list[PageBlock], 
        doc_name: str
    ) -> list[Chunk]:
        """
        主切块方法：章节感知 + token上限控制
        """
        sections = self._blocks_to_sections(blocks)
        chunks = []
        chunk_index = 0
        
        for section in sections:
            section_text = "\n\n".join(b.content for b in section["blocks"])
            section_tokens = self._estimate_tokens(section_text)
            
            if section_tokens <= self.max_tokens:
                # 章节本身不超限：整个章节作为一个chunk
                chunk_id = f"{doc_name}_{chunk_index:03d}"
                chunks.append(Chunk(
                    chunk_id=chunk_id,
                    text=section_text,
                    metadata={
                        "source": doc_name,
                        "title": section["title"],
                        "section_level": section["level"],
                        "page_range": [section["start_page"], section["end_page"]],
                        "start_page": section["start_page"],
                        "end_page": section["end_page"],
                        "chunk_index": chunk_index,
                        "token_count": section_tokens,
                    }
                ))
                chunk_index += 1
            else:
                # 超长章节：按段落进一步切分，保持overlap
                sub_chunks = self._split_long_section(
                    section, doc_name, chunk_index
                )
                chunks.extend(sub_chunks)
                chunk_index += len(sub_chunks)
        
        return chunks
    
    def _split_long_section(
        self, 
        section: dict, 
        doc_name: str, 
        start_index: int
    ) -> list[Chunk]:
        """对超长章节进行带overlap的段落级切分"""
        paragraphs = []
        for block in section["blocks"]:
            # 表格作为原子单元不切分
            if block.block_type == "table":
                paragraphs.append({"text": block.content, "page": block.page_num})
            else:
                # 文本按段落（双换行）分割
                for para in block.content.split("\n\n"):
                    para = para.strip()
                    if para:
                        paragraphs.append({"text": para, "page": block.page_num})
        
        chunks = []
        current_texts = []
        current_tokens = 0
        current_pages = set()
        chunk_idx = start_index
        
        for para in paragraphs:
            para_tokens = self._estimate_tokens(para["text"])
            
            if current_tokens + para_tokens > self.max_tokens and current_texts:
                # 输出当前chunk
                page_list = sorted(current_pages)
                chunk_text = "\n\n".join(current_texts)
                
                chunks.append(Chunk(
                    chunk_id=f"{doc_name}_{chunk_idx:03d}",
                    text=chunk_text,
                    metadata={
                        "source": doc_name,
                        "title": section["title"],
                        "section_level": section["level"],
                        "page_range": [min(page_list), max(page_list)],
                        "start_page": min(page_list),
                        "end_page": max(page_list),
                        "chunk_index": chunk_idx,
                        "token_count": self._estimate_tokens(chunk_text),
                    }
                ))
                chunk_idx += 1
                
                # Overlap：保留最后N个token的段落
                overlap_texts = []
                overlap_tokens = 0
                for t in reversed(current_texts):
                    t_tok = self._estimate_tokens(t)
                    if overlap_tokens + t_tok > self.overlap_tokens:
                        break
                    overlap_texts.insert(0, t)
                    overlap_tokens += t_tok
                
                current_texts = overlap_texts + [para["text"]]
                current_tokens = overlap_tokens + para_tokens
                current_pages = {para["page"]}
            else:
                current_texts.append(para["text"])
                current_tokens += para_tokens
                current_pages.add(para["page"])
        
        # 处理最后剩余内容
        if current_texts:
            page_list = sorted(current_pages)
            chunk_text = "\n\n".join(current_texts)
            chunks.append(Chunk(
                chunk_id=f"{doc_name}_{chunk_idx:03d}",
                text=chunk_text,
                metadata={
                    "source": doc_name,
                    "title": section["title"],
                    "section_level": section["level"],
                    "page_range": [min(page_list), max(page_list)],
                    "start_page": min(page_list),
                    "end_page": max(page_list),
                    "chunk_index": chunk_idx,
                    "token_count": self._estimate_tokens(chunk_text),
                }
            ))
        
        return chunks
```

------

#### Layer 3：Pipeline整合与输出

```python
class FinancialPDFPipeline:
    """完整处理流水线"""
    
    def __init__(
        self,
        max_tokens: int = 1024,
        overlap_tokens: int = 128,
    ):
        self.chunker = SemanticChunker(max_tokens, overlap_tokens)
    
    def process(self, pdf_path: str, output_jsonl: str) -> list[Chunk]:
        """
        处理单个PDF，输出JSONL
        
        输出的chunk metadata示例：
        {
          "chunk_id": "半导体双周报_004",
          "text": "...",
          "metadata": {
            "source": "半导体双周报.pdf",
            "title": "一、市场动态",
            "section_level": 2,
            "start_page": 3,        ← 精确页码（来自fitz，非启发式推断）
            "end_page": 4,
            "page_range": [3, 4],
            "chunk_index": 4,
            "token_count": 512
          }
        }
        """
        doc_name = Path(pdf_path).stem
        
        # Step 1: 结构感知提取
        extractor = FinancialPDFExtractor(pdf_path)
        try:
            blocks = extractor.extract_all()
        finally:
            extractor.close()
        
        # Step 2: 语义切块（自动携带页码）
        chunks = self.chunker.chunk(blocks, doc_name)
        
        # Step 3: 输出JSONL
        with open(output_jsonl, "w", encoding="utf-8") as f:
            for chunk in chunks:
                record = {
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "metadata": chunk.metadata,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        
        return chunks
    
    def process_batch(
        self, 
        pdf_dir: str, 
        output_dir: str
    ) -> dict:
        """批量处理目录下所有PDF"""
        pdf_dir = Path(pdf_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)
        
        stats = {"success": 0, "failed": 0, "total_chunks": 0}
        
        for pdf_file in pdf_dir.glob("*.pdf"):
            output_path = output_dir / f"{pdf_file.stem}.jsonl"
            try:
                chunks = self.process(str(pdf_file), str(output_path))
                stats["success"] += 1
                stats["total_chunks"] += len(chunks)
                print(f"✓ {pdf_file.name}: {len(chunks)} chunks")
            except Exception as e:
                stats["failed"] += 1
                print(f"✗ {pdf_file.name}: {e}")
        
        return stats


# 使用示例
if __name__ == "__main__":
    pipeline = FinancialPDFPipeline(max_tokens=1024, overlap_tokens=128)
    
    # 单文件处理
    chunks = pipeline.process(
        "半导体行业双周报.pdf",
        "output/半导体行业双周报.jsonl"
    )
    
    # 验证页码元数据
    for chunk in chunks[:3]:
        print(f"ID: {chunk.chunk_id}")
        print(f"页码: {chunk.metadata['start_page']}-{chunk.metadata['end_page']}")
        print(f"章节: {chunk.metadata['title']}")
        print("---")
```

------

## 四、决策矩阵总结

| 问题        | 临时方案          | 推荐方案              | 原因                                    |
| ----------- | ----------------- | --------------------- | --------------------------------------- |
| PDF质量差   | 调pymupdf4llm参数 | fitz+pdfplumber双引擎 | 金融文档复杂度超出单工具能力边界        |
| 页码缺失    | AI从MD推断        | 提取阶段直接绑定      | 元数据应由确定性代码生成，不依赖LLM猜测 |
| 表格混乱    | 接受loss          | pdfplumber专项处理    | 财报核心数据不能丢失                    |
| 按token硬切 | 增大chunk size    | 章节感知语义切块      | RAG召回精度取决于chunk语义完整性        |

**不建议临时方案**——当前基线数据集的质量直接决定了后续所有评估的可信度，在基础设施上妥协会导致评估结论失真。

