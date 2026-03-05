import os
import chromadb
from chromadb.utils import embedding_functions
from config import Config


def build_embedding():
    """根据 EMBED_TYPE 构建对应的 ChromaDB EmbeddingFunction。"""
    embed_type = Config.EMBED_TYPE.lower()

    if embed_type == "local":
        # 纯本地：通过 sentence-transformers 加载 HuggingFace 模型
        # 首次运行会自动从 HuggingFace 下载权重（约 600 MB）
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=Config.EMBED_LOCAL_MODEL,
            device=Config.EMBED_LOCAL_DEVICE,
        )

    elif embed_type == "ollama":
        # Ollama 本地服务，需提前执行:
        #   ollama pull qwen3-embedding:0.6b
        return embedding_functions.OllamaEmbeddingFunction(
            model_name=Config.EMBED_OLLAMA_MODEL,
            url=Config.EMBED_OLLAMA_URL,
        )

    elif embed_type == "api":
        # 兼容 OpenAI 接口的远程 API
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=Config.EMBED_API_KEY,
            api_base=Config.EMBED_API_BASE,
            model_name=Config.EMBED_MODEL,
        )

    else:
        raise ValueError(
            f"不支持的 EMBED_TYPE='{Config.EMBED_TYPE}'，请在 .env 中设置为 local / ollama / api"
        )


class LongTermMemory:
    def __init__(self):
        # 将相对路径转为绝对路径，避免 Windows 下 Streamlit 热重载时工作目录漂移
        # 导致 ChromaDB Rust 后端触发 ERROR_ALREADY_EXISTS (os error 183)
        db_path = os.path.abspath(Config.VECTOR_DB_PATH)
        os.makedirs(db_path, exist_ok=True)

        # 持久化向量数据库
        self.client = chromadb.PersistentClient(path=db_path)

        # 根据配置选择 embedding 方案
        self.embedding_fn = build_embedding()

        self.collection = self.client.get_or_create_collection(
            name="agent_memories",
            embedding_function=self.embedding_fn
        )

    def get_all(self) -> list[dict]:
        """返回集合中所有记忆，格式为 [{"fact": ...}, ...]"""
        result = self.collection.get()
        return [{"fact": doc} for doc in result["documents"]]

    def __len__(self) -> int:
        return self.collection.count()

    def add_memory(self, fact: str, metadata: dict = None):
        """将事实存入向量数据库"""
        # 自动生成一个唯一的 ID
        import uuid
        mem_id = str(uuid.uuid4())
        
        self.collection.add(
            documents=[fact],
            metadatas=[metadata] if metadata else [{"source": "user_input"}],
            ids=[mem_id]
        )

    def retrieve(self, query: str, top_k: int = 3) -> list[dict]:
        """
        使用语义检索最相关的记忆
        返回结果包含：事实内容、元数据、相似度得分
        """
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k
        )
        
        # 格式化输出
        formatted_results = []
        # results['documents'][0] 是匹配到的文本列表
        for i in range(len(results['documents'][0])):
            formatted_results.append({
                "fact": results['documents'][0][i],
                "metadata": results['metadatas'][0][i],
                "distance": results['distances'][0][i] # 距离越小越相关
            })
            
        return formatted_results