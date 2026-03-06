"""
knowledge/store.py — 只读知识库
================================
KnowledgeStore 对外只暴露检索接口（retrieve / search），
写入方法以单下划线标注，仅供 KnowledgeLoader 在初始化阶段调用。
RAG 流程中 AgentMemory 只持有 KnowledgeStore，从根本上
确保运行期间无法向知识库写入任何内容。
"""

import os
import uuid
import chromadb

from config import Config
from src.utils.embedding import build_embedding


class KnowledgeStore:
    """
    只读知识库。

    使用与 LongTermMemory 相同的向量数据库目录，
    但存储在独立的 Collection（默认 `knowledge_base`）中，
    与记忆数据完全隔离。
    """

    def __init__(self, collection_name: str | None = None):
        collection_name = collection_name or Config.KB_COLLECTION
        db_path = os.path.abspath(Config.VECTOR_DB_PATH)
        os.makedirs(db_path, exist_ok=True)

        self._client = chromadb.PersistentClient(path=db_path)
        self._embedding_fn = build_embedding()
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=self._embedding_fn,
        )

    # ================================================================
    # 公开只读接口
    # ================================================================

    def retrieve(self, query: str, top_k: int | None = None) -> list[dict]:
        """
        语义检索与 query 最相关的知识片段。

        返回列表，每项格式：
          {"text": str, "source": str, "distance": float}
        """
        top_k = top_k or Config.KB_TOP_K
        count = self._collection.count()
        if count == 0:
            return []
        top_k = min(top_k, count)

        results = self._collection.query(
            query_texts=[query],
            n_results=top_k,
        )
        return [
            {
                "text": results["documents"][0][i],
                "source": (results["metadatas"][0][i] or {}).get("source", ""),
                "distance": results["distances"][0][i],
            }
            for i in range(len(results["documents"][0]))
        ]

    def count(self) -> int:
        """返回知识库中的文档块数量。"""
        return self._collection.count()

    def get_all(self) -> list[dict]:
        """返回所有文档块（仅用于展示 / 调试）。"""
        result = self._collection.get()
        return [
            {
                "text": doc,
                "source": (meta or {}).get("source", ""),
                "chunk_index": (meta or {}).get("chunk_index", ""),
            }
            for doc, meta in zip(result["documents"], result["metadatas"])
        ]

    def list_sources(self) -> list[str]:
        """返回已导入的来源文件名列表（去重）。"""
        result = self._collection.get()
        sources = {(meta or {}).get("source", "") for meta in result["metadatas"]}
        return sorted(s for s in sources if s)

    def __len__(self) -> int:
        return self._collection.count()

    def __repr__(self) -> str:
        return f"KnowledgeStore(chunks={self.count()}, sources={self.list_sources()})"

    # ================================================================
    # 内部写入接口（仅供 KnowledgeLoader 调用，不对外暴露）
    # ================================================================

    def _add_chunk(self, text: str, metadata: dict | None = None) -> None:
        """写入单个文本块。外部代码不应直接调用此方法。"""
        self._collection.add(
            documents=[text],
            metadatas=[metadata or {}],
            ids=[str(uuid.uuid4())],
        )

    def _delete_source(self, source: str) -> None:
        """删除指定来源的所有块（用于重新加载文件时清理旧数据）。"""
        result = self._collection.get(where={"source": source})
        if result["ids"]:
            self._collection.delete(ids=result["ids"])
