```
用户输入
  │
  ▼  ── 快速路径（前端，同步）──────────────────────────────────
  │  build_messages()
  │    ├─ 全量静态记忆（固定属性）      ──┐
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
记忆分层
层级	存储	内容	注入方式
静态记忆	MongoDB（降级 JSON）	姓名、职业、居住地等固定属性	全量注入 System Prompt
动态记忆	ChromaDB	近期状态、偏好、观点	向量检索 top-k
知识库	ChromaDB（独立 collection）	只读领域文档	向量检索 top-k
冲突处理
整理线程检测到矛盾 → ConflictItem 入队
每次页面渲染检查冲突队列 → 顶部显示对比卡片（已有记忆 vs 新记忆）
用户点击「确认更新」/ 「保留原记忆」→ resolve_conflict() 执行写入或丢弃