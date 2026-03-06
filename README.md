# Agent Memory

具备分层记忆能力的 AI 对话助手，基于 Streamlit + OpenAI 兼容接口构建。

## 快速开始

```bash
pip install -r requirements.txt
# 复制并填写 .env 配置（API Key、模型、Embedding 方式等）
streamlit run app.py
```

## 数据流

```
用户输入
  │
  ▼  ── 快速路径（前端，同步）──────────────────────────────────
  │  build_messages()
  │    ├─ 全量静态记忆（固定属性）       ──┐
  │    ├─ 向量检索动态记忆                ├─→ System Prompt → LLM → 回复
  │    └─ 向量检索知识库                ──┘
  │
  ▼  ── 整理路径（后台线程，异步）──────────────────────────────
  │
  ├─ auto_extract=ON  → 每次回复后 submit_for_consolidation()
  └─ auto_extract=OFF → FIFO 弹出消息时自动触发
          │
          ▼  MemoryConsolidator（独立 daemon 线程）
          │
          1. LLM 提取 → static facts + dynamic facts
          2. 检索相似已有记忆
          3. LLM 比对：ADD / UPDATE / CONFLICT
                    │
          ┌─────────┼──────────┐
          ▼         ▼          ▼
        ADD       UPDATE    CONFLICT
      直接写入   记忆融合   推送冲突队列
                          ↓
                   前端渲染时检测 → 弹出确认卡片
```

## 记忆分层

| 层级 | 存储 | 内容 | 注入方式 |
|---|---|---|---|
| 短期记忆 | 内存（FIFO 队列） | 最近 N 轮对话消息 | 直接拼入 messages |
| 静态记忆 | MongoDB（降级 JSON） | 姓名、职业、居住地等固定属性 | 全量注入 System Prompt |
| 动态记忆 | ChromaDB | 近期状态、偏好、观点 | 向量检索 top-k |
| 知识库 | ChromaDB（独立 collection） | 只读领域文档 | 向量检索 top-k |

## 冲突处理

整理线程检测到矛盾 → `ConflictItem` 入队  
每次页面渲染检查冲突队列 → 顶部显示对比卡片（已有记忆 vs 新记忆）  
用户点击「确认更新」/「保留原记忆」→ `resolve_conflict()` 执行写入或丢弃

---

## 项目结构

```
Memory/
├── app.py                        # Streamlit 前端入口，对话界面 + 侧边栏记忆管理
├── config.py                     # 配置中心，从 .env 加载所有参数（LLM、Embedding、DB 等）
├── requirements.txt              # Python 依赖列表
│
├── data/
│   ├── static_memory.json        # MongoDB 不可用时的静态记忆 JSON 备用后端
│   └── chroma/                   # ChromaDB 持久化目录（动态记忆 + 知识库）
│
├── assets/                       # 静态资源（favicon 等）
│
├── src/
│   ├── agent/
│   │   └── brain.py              # （预留）Agent 决策核心，暂未实现
│   │
│   ├── memory/
│   │   ├── manager.py            # AgentMemory：统一管理四层记忆的门面类
│   │   ├── short_term.py         # ShortTermMemory：FIFO 对话窗口，满载时触发整理
│   │   ├── long_term.py          # LongTermMemory：动态长期记忆，ChromaDB 向量存储
│   │   ├── static_memory.py      # StaticMemory：静态长期记忆，MongoDB / JSON 双后端
│   │   └── consolidator.py       # MemoryConsolidator：后台 daemon 线程，LLM 提取 + 去重
│   │
│   ├── knowledge/
│   │   ├── store.py              # KnowledgeStore：只读知识库，语义检索接口
│   │   └── loader.py             # KnowledgeLoader：文档分块写入工具（管理员使用）
│   │
│   └── utils/
│       ├── embedding.py          # build_embedding()：按配置构建 ChromaDB EmbeddingFunction
│       │                         #   支持 local（sentence-transformers）/ ollama / api 三种模式
│       └── llm.py                # build_consolidate_llm()：Consolidator 专用 LLM 调用工厂
│                                 #   支持 api（OpenAI 兼容）/ ollama（原生客户端）/ local（transformers）
│
└── demo/                         # 独立演示脚本（不依赖 Streamlit）
    ├── memory.py                 # 最基础版本：关键词检索 + 纯内存长期记忆
    ├── memory_with_embedding.py  # 进阶版本：引入 LongTermMemory 语义检索
    ├── memory_with_extract.py    # 进阶版本：引入 LLM 自动提取事实
    └── load_knowledge.py         # CLI 工具：将本地文档（txt/md/pdf）导入知识库
```

### 各模块职责速查

| 文件 | 核心职责 |
|---|---|
| `app.py` | Streamlit UI，对话主循环，冲突卡片渲染，侧边栏记忆展示与手动写入 |
| `config.py` | 唯一配置入口，`cfg` 全局单例，所有参数均可通过 `.env` 覆盖 |
| `manager.py` | 门面（Facade），对外暴露 `add_message` / `build_messages` / `resolve_conflict` 等接口 |
| `short_term.py` | 有界 FIFO 队列；`add_memory()` 返回被弹出的消息供 Consolidator 消费 |
| `long_term.py` | 封装 ChromaDB `agent_memories` collection；支持语义 `retrieve` 和 `delete_by_id` |
| `static_memory.py` | MongoDB 主后端 + JSON 文件降级；存储不常变更的用户固定属性 |
| `consolidator.py` | 后台线程；通过 `build_consolidate_llm()` 驱动提取与比对，支持三种 LLM 模式 |
| `store.py` | 封装 ChromaDB `knowledge_base` collection；运行期对 Agent 只读 |
| `loader.py` | 文本分块（滑动窗口）→ 写入 `KnowledgeStore`；仅供管理脚本调用 |
| `embedding.py` | 工厂函数，统一为 `LongTermMemory` 和 `KnowledgeStore` 提供相同的向量化策略 |
| `llm.py` | 工厂函数，为 `MemoryConsolidator` 构建 LLM 调用 callable；支持独立于对话模型的 api / ollama / local |