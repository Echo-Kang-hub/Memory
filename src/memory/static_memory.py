"""
memory/static_memory.py — 静态长期记忆
=========================================
存储用户的固定属性：姓名、职业、居住地、家庭关系、长期偏好等。

主后端：MongoDB（pymongo）
备用后端：本地 JSON 文件（MongoDB 不可用时自动降级，数据持久化）
"""

import json
import os
import uuid
from datetime import datetime

from config import Config


class StaticMemory:
    """
    静态长期记忆。

    特点：条目少、强结构、人工可读，不需要向量化。
    在 build_messages 时全量注入到 System Prompt 的"用户固定信息"区块。
    """

    def __init__(self, json_path: str | None = None, collection_name: str | None = None):
        self._backend: str = "json"
        self._collection = None
        self._collection_name = collection_name or Config.MONGO_STATIC_COLLECTION
        self._json_path = os.path.abspath(json_path or "./data/static_memory.json")
        self._init_backend()

    # ================================================================
    # 公开增删改查接口
    # ================================================================

    def add(self, fact: str, metadata: dict | None = None) -> str:
        """写入一条静态事实，返回新记录的 ID。"""
        now = datetime.utcnow().isoformat()
        if self._backend == "mongodb":
            result = self._collection.insert_one(
                {"fact": fact, "metadata": metadata or {}, "created_at": now, "updated_at": now}
            )
            return str(result.inserted_id)
        else:
            data = self._load()
            doc_id = str(uuid.uuid4())
            data.append(
                {"id": doc_id, "fact": fact, "metadata": metadata or {},
                 "created_at": now, "updated_at": now}
            )
            self._save(data)
            return doc_id

    def update(self, fact_id: str, new_fact: str) -> None:
        """更新指定 ID 的事实内容（用于记忆融合）。"""
        now = datetime.utcnow().isoformat()
        if self._backend == "mongodb":
            from bson import ObjectId
            self._collection.update_one(
                {"_id": ObjectId(fact_id)},
                {"$set": {"fact": new_fact, "updated_at": now}},
            )
        else:
            data = self._load()
            for doc in data:
                if doc["id"] == fact_id:
                    doc["fact"] = new_fact
                    doc["updated_at"] = now
                    break
            self._save(data)

    def delete(self, fact_id: str) -> None:
        """删除指定 ID 的事实。"""
        if self._backend == "mongodb":
            from bson import ObjectId
            self._collection.delete_one({"_id": ObjectId(fact_id)})
        else:
            data = self._load()
            self._save([d for d in data if d["id"] != fact_id])

    def get_all(self) -> list[dict]:
        """返回所有静态记忆，格式：[{"id": ..., "fact": ..., "metadata": ...}]"""
        if self._backend == "mongodb":
            return [
                {"id": str(doc["_id"]), "fact": doc["fact"],
                 "metadata": doc.get("metadata", {})}
                for doc in self._collection.find()
            ]
        return [
            {"id": d["id"], "fact": d["fact"], "metadata": d.get("metadata", {})}
            for d in self._load()
        ]

    def get_all_text(self) -> list[str]:
        """仅返回所有事实的文本，用于注入 System Prompt。"""
        return [item["fact"] for item in self.get_all()]

    def clear_all(self) -> None:
        """清空所有静态记忆（用于测试重置）"""
        if self._backend == "mongodb":
            self._collection.delete_many({})
        else:
            self._save([])

    def __len__(self) -> int:
        if self._backend == "mongodb":
            return self._collection.count_documents({})
        return len(self._load())

    @property
    def backend(self) -> str:
        return self._backend

    def __repr__(self) -> str:
        return f"StaticMemory(backend={self._backend}, count={len(self)})"

    # ================================================================
    # 内部方法
    # ================================================================

    def _init_backend(self) -> None:
        try:
            from pymongo import MongoClient
            client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=3000)
            client.server_info()  # 快速连通性测试
            self._collection = client[Config.MONGO_DB][self._collection_name]
            self._backend = "mongodb"
        except Exception as exc:
            print(f"[StaticMemory] MongoDB 不可用，降级使用 JSON 文件：{exc}")
            os.makedirs(os.path.dirname(self._json_path), exist_ok=True)
            if not os.path.exists(self._json_path):
                self._save([])

    def _load(self) -> list[dict]:
        with open(self._json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: list[dict]) -> None:
        with open(self._json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
