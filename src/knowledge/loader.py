"""
knowledge/loader.py — 知识库文档加载器
========================================
管理员工具，负责将文档（txt / md / pdf）分块并写入 KnowledgeStore。
运行期间 AgentMemory 不持有 Loader，从而确保知识库对 Agent 只读。

用法（单独脚本中）：
    from src.knowledge.store  import KnowledgeStore
    from src.knowledge.loader import KnowledgeLoader

    store  = KnowledgeStore()
    loader = KnowledgeLoader(store)
    loader.load_file("docs/product_manual.md")
    loader.load_directory("docs/", extensions=[".txt", ".md"])
"""

import os
from pathlib import Path
from config import Config
from src.knowledge.store import KnowledgeStore


class KnowledgeLoader:
    """
    文档加载器。

    职责：读取文件 → 文本切块 → 写入 KnowledgeStore._add_chunk()。
    只有显式构造 KnowledgeLoader 才能触发写入，AgentMemory 不会创建它。
    """

    def __init__(self, store: KnowledgeStore):
        self._store = store

    # ================================================================
    # 公开加载接口
    # ================================================================

    def load_text(
        self,
        text: str,
        source: str = "manual",
        chunk_size: int | None = None,
        overlap: int | None = None,
        reload: bool = False,
    ) -> int:
        """
        加载纯文本字符串。

        Args:
            text:       原始文本内容。
            source:     来源标识（例如文件名），写入 metadata。
            chunk_size: 每块字符数，None 时读取配置。
            overlap:    相邻块重叠字符数，None 时读取配置。
            reload:     为 True 时先删除同名来源的旧数据再写入。
        Returns:
            写入的块数。
        """
        chunk_size = chunk_size or Config.KB_CHUNK_SIZE
        overlap = overlap or Config.KB_CHUNK_OVERLAP

        if reload:
            self._store._delete_source(source)

        chunks = self._chunk_text(text, chunk_size, overlap)
        for idx, chunk in enumerate(chunks):
            self._store._add_chunk(
                text=chunk,
                metadata={"source": source, "chunk_index": idx},
            )
        return len(chunks)

    def load_file(
        self,
        file_path: str,
        chunk_size: int | None = None,
        overlap: int | None = None,
        reload: bool = True,
    ) -> int:
        """
        加载单个文件（.txt / .md / .pdf）。

        Args:
            file_path: 文件绝对或相对路径。
            chunk_size: 每块字符数，None 时读取配置。
            overlap:   相邻块重叠字符数，None 时读取配置。
            reload:    默认 True：若该文件已导入则先清除旧数据。
        Returns:
            写入的块数。
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在：{file_path}")

        ext = path.suffix.lower()
        if ext == ".pdf":
            text = self._read_pdf(path)
        elif ext in (".txt", ".md", ".markdown"):
            text = path.read_text(encoding="utf-8")
        else:
            raise ValueError(
                f"不支持的文件类型 '{ext}'，仅支持 .txt / .md / .pdf"
            )

        source = path.name
        return self.load_text(
            text=text,
            source=source,
            chunk_size=chunk_size,
            overlap=overlap,
            reload=reload,
        )

    def load_directory(
        self,
        dir_path: str,
        extensions: list[str] | None = None,
        chunk_size: int | None = None,
        overlap: int | None = None,
        reload: bool = True,
    ) -> dict[str, int]:
        """
        批量加载目录中的所有文档。

        Args:
            dir_path:   目录路径。
            extensions: 要处理的扩展名列表，默认 [".txt", ".md", ".pdf"]。
            chunk_size: 每块字符数。
            overlap:    相邻块重叠字符数。
            reload:     是否覆盖已存在的同名来源。
        Returns:
            {文件名: 写入块数} 的字典。
        """
        extensions = extensions or [".txt", ".md", ".markdown", ".pdf"]
        dir_path = Path(dir_path)
        if not dir_path.is_dir():
            raise NotADirectoryError(f"目录不存在：{dir_path}")

        results: dict[str, int] = {}
        for file in sorted(dir_path.rglob("*")):
            if file.suffix.lower() in extensions and file.is_file():
                try:
                    n = self.load_file(
                        str(file), chunk_size=chunk_size, overlap=overlap, reload=reload
                    )
                    results[file.name] = n
                except Exception as exc:
                    results[file.name] = -1
                    print(f"[KnowledgeLoader] 跳过 {file.name}：{exc}")
        return results

    # ================================================================
    # 内部工具
    # ================================================================

    @staticmethod
    def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
        """
        滑动窗口切块（按字符数）。
        先尝试在句号/换行处断行，保持语义完整性；
        若段落过长则强制按 chunk_size 截断。
        """
        # 先按段落（连续换行）粗切
        paragraphs: list[str] = []
        for para in text.split("\n\n"):
            para = para.strip()
            if para:
                paragraphs.append(para)

        chunks: list[str] = []
        buffer = ""

        for para in paragraphs:
            # 段落本身超长 → 强制按字符切
            if len(para) > chunk_size:
                if buffer:
                    chunks.append(buffer.strip())
                    buffer = ""
                start = 0
                while start < len(para):
                    end = start + chunk_size
                    chunks.append(para[start:end].strip())
                    start = end - overlap
                continue

            if len(buffer) + len(para) + 2 <= chunk_size:
                buffer = buffer + "\n\n" + para if buffer else para
            else:
                if buffer:
                    chunks.append(buffer.strip())
                # 用上一块末尾作为 overlap
                if overlap > 0 and buffer:
                    overlap_text = buffer[-overlap:]
                    buffer = overlap_text + "\n\n" + para
                else:
                    buffer = para

        if buffer.strip():
            chunks.append(buffer.strip())

        return [c for c in chunks if c]

    @staticmethod
    def _read_pdf(path: Path) -> str:
        """读取 PDF 文件文本（依赖 pypdf，可选安装）。"""
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError:
            raise ImportError(
                "读取 PDF 需要安装 pypdf：pip install pypdf"
            )
        reader = PdfReader(str(path))
        return "\n\n".join(
            page.extract_text() or "" for page in reader.pages
        )
