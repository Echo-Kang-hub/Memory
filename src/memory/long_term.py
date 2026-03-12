import os
import chromadb
from config import Config
from src.utils.embedding import build_embedding


class LongTermMemory:
    def __init__(self, collection_name: str = "agent_memories"):
        # 将相对路径转为绝对路径，避免 Windows 下 Streamlit 热重载时工作目录漂移
        # 导致 ChromaDB Rust 后端触发 ERROR_ALREADY_EXISTS (os error 183)
        db_path = os.path.abspath(Config.VECTOR_DB_PATH)
        os.makedirs(db_path, exist_ok=True)

        # 持久化向量数据库
        self.client = chromadb.PersistentClient(path=db_path)

        # 根据配置选择 embedding 方案
        self.embedding_fn = build_embedding()

        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_fn
        )

    def get_all(self) -> list[dict]:
        """返回集合中所有记忆，格式为 [{"id": ..., "fact": ...}, ...]"""
        result = self.collection.get()
        return [
            {"id": mem_id, "fact": doc}
            for mem_id, doc in zip(result["ids"], result["documents"])
        ]

    def __len__(self) -> int:
        return self.collection.count()

    def add_memory(self, fact: str, metadata: dict = None):
        """将事实存入向量数据库"""
        import uuid
        mem_id = str(uuid.uuid4())
        
        self.collection.add(
            documents=[fact],
            metadatas=[metadata] if metadata else [{"source": "user_input"}],
            ids=[mem_id]
        )

    def delete_by_id(self, mem_id: str) -> None:
        """删除指定 ID 的动态记忆"""
        self.collection.delete(ids=[mem_id])

    def clear_all(self) -> None:
        """删除集合中所有记忆（用于测试重置）"""
        ids = self.collection.get()["ids"]
        if ids:
            self.collection.delete(ids=ids)

    def retrieve(self, query: str, top_k: int = 3) -> list[dict]:
        """
        使用语义检索最相关的记忆
        返回结果包含：事实内容、元数据、相似度得分
        """
        results = self.collection.query(
            query_texts=[query],
            n_results=min(top_k, self.collection.count() or 1)
        )
        
        formatted_results = []
        for i in range(len(results['documents'][0])):
            formatted_results.append({
                "id":       results['ids'][0][i],
                "fact":     results['documents'][0][i],
                "metadata": results['metadatas'][0][i],
                "distance": results['distances'][0][i],
            })
            
        return formatted_results