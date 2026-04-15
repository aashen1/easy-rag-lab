import argparse

from loguru import logger

from src.pipeline import RAGPipeline
from src.utils import load_config, setup_logger


def interactive_chat(pipeline: RAGPipeline) -> None:
    collection_info = pipeline.indexer.get_collection_info()
    if collection_info:
        chunks_count = collection_info.get("points_count", 0)
        print(f"\n🤖 RAG 问答系统已启动（输入 'quit' 或 'exit' 退出）")
        print(f"📝 数据库中已有 {chunks_count} 个文档片段\n")
    else:
        print("\n🤖 RAG 问答系统已启动（输入 'quit' 或 'exit' 退出）")
        print("⚠️  数据库为空，请先构建索引：pixi run python main.py --build-index\n")

    while True:
        try:
            query = input("💬 You: ").strip()

            if not query:
                continue

            if query.lower() in ["quit", "exit", "q"]:
                print("👋 再见！\n")
                break

            result = pipeline.query(query)

            print(f"\n🤖 Assistant: {result['answer']}\n")

            if "sources" in result and result["sources"]:
                print("📚 参考来源：")
                for i, (source, score) in enumerate(
                    zip(result["sources"][:3], result["scores"][:3]), 1
                ):
                    source_name = source.split("\\")[-1] if "\\" in source else source
                    print(f"   {i}. {source_name} (相关度: {score:.4f})")
                print()

        except KeyboardInterrupt:
            print("\n\n👋 再见！\n")
            break
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            print(f"\n❌ 处理问题时出错: {str(e)}\n")


def main():
    parser = argparse.ArgumentParser(description="Interactive RAG Q&A System")
    parser.add_argument(
        "--config", type=str, default="config.yaml", help="Config file path"
    )
    parser.add_argument(
        "--llm-preset", type=str, help="LLM preset name (default, opus, sonnet, haiku)"
    )

    args = parser.parse_args()

    config = load_config(args.config)
    setup_logger(config)

    pipeline = RAGPipeline(config_path=args.config, llm_preset=args.llm_preset)

    interactive_chat(pipeline)


if __name__ == "__main__":
    main()
