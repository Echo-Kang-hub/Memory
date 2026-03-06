"""
demo/load_knowledge.py — 知识库管理脚本
==========================================
用于将本地文档导入只读知识库。此脚本独立于 Agent 运行，
导入完成后知识库对 Agent 只读，不允许在对话过程中修改。

用法示例：
  # 加载单个文件
  python demo/load_knowledge.py --file docs/product_manual.md

  # 加载整个目录
  python demo/load_knowledge.py --dir docs/

  # 查看知识库当前状态
  python demo/load_knowledge.py --status

  # 清空并重新加载
  python demo/load_knowledge.py --dir docs/ --reload
"""

import sys
import os
import argparse

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.knowledge.store import KnowledgeStore
from src.knowledge.loader import KnowledgeLoader
from config import cfg


def cmd_status(store: KnowledgeStore) -> None:
    """打印知识库状态。"""
    count = store.count()
    sources = store.list_sources()
    print(f"\n{'─'*50}")
    print(f"  知识库状态")
    print(f"{'─'*50}")
    print(f"  文档块总数 : {count}")
    print(f"  来源文件数 : {len(sources)}")
    if sources:
        print(f"  来源列表   :")
        for src in sources:
            # 统计该来源的块数
            all_chunks = store.get_all()
            n = sum(1 for c in all_chunks if c["source"] == src)
            print(f"    • {src}  ({n} 块)")
    print(f"{'─'*50}\n")


def cmd_load_file(store: KnowledgeStore, file_path: str, reload: bool) -> None:
    loader = KnowledgeLoader(store)
    print(f"正在加载文件：{file_path} ...")
    n = loader.load_file(file_path, reload=reload)
    print(f"✔ 完成，写入 {n} 个块。")


def cmd_load_dir(store: KnowledgeStore, dir_path: str, reload: bool) -> None:
    loader = KnowledgeLoader(store)
    print(f"正在加载目录：{dir_path} ...")
    results = loader.load_directory(dir_path, reload=reload)
    total = sum(n for n in results.values() if n >= 0)
    failed = [f for f, n in results.items() if n < 0]
    print(f"✔ 完成，共写入 {total} 个块，涉及 {len(results)} 个文件。")
    if failed:
        print(f"✘ 以下文件加载失败：{failed}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="知识库管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file",   metavar="PATH", help="加载单个文件 (.txt/.md/.pdf)")
    group.add_argument("--dir",    metavar="PATH", help="批量加载目录中的所有文档")
    group.add_argument("--status", action="store_true", help="查看知识库当前状态")

    parser.add_argument(
        "--reload",
        action="store_true",
        default=True,
        help="重新加载时先清除同名来源的旧数据（默认 True）",
    )
    parser.add_argument(
        "--collection",
        default=cfg.KB_COLLECTION,
        help=f"ChromaDB collection 名称（默认：{cfg.KB_COLLECTION}）",
    )

    args = parser.parse_args()
    store = KnowledgeStore(collection_name=args.collection)

    if args.status:
        cmd_status(store)
    elif args.file:
        cmd_load_file(store, args.file, reload=args.reload)
        cmd_status(store)
    elif args.dir:
        cmd_load_dir(store, args.dir, reload=args.reload)
        cmd_status(store)


if __name__ == "__main__":
    main()
