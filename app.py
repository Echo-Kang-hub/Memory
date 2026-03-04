"""
app.py - Agent Memory MVP
streamlit run app.py
"""

import streamlit as st
from openai import OpenAI
from memory import AgentMemory
from config import cfg

# == 页面配置 ==
st.set_page_config(page_title="Agent Memory", page_icon="🧠", layout="wide")
st.title("🧠 Agent Memory（最小可行版本）")

# == 状态初始化（使用 config 参数）==
if "memory" not in st.session_state:
    st.session_state.memory = AgentMemory(short_term_limit=cfg.SHORT_TERM_LIMIT)
if "chat_log" not in st.session_state:
    st.session_state.chat_log = []

memory: AgentMemory = st.session_state.memory

# == 侧边栏 ==
with st.sidebar:
    st.header("⚙️ 配置")

    # 模型可在运行时覆盖，默认读取 .env 中的 MODEL
    model = st.selectbox(
        "模型",
        ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo", "deepseek-chat", "custom"],
        index=["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo", "deepseek-chat", "custom"].index(cfg.MODEL)
        if cfg.MODEL in ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo", "deepseek-chat", "custom"]
        else 0,
    )
    if model == "custom":
        model = st.text_input("自定义模型名", value=cfg.MODEL)

    # 显示当前 .env 中的服务配置（只读提示，不暴露完整 key）
    key_preview = f"{cfg.API_KEY[:8]}..." if cfg.API_KEY else "⚠️ 未设置"
    st.caption(f"BASE_URL: `{cfg.BASE_URL}`")
    st.caption(f"API_KEY: `{key_preview}`")

    st.divider()
    st.header("📚 长期记忆")

    new_fact = st.text_input("手动写入事实", placeholder="例：用户叫小明，喜欢 Python")
    if st.button("写入记忆") and new_fact:
        memory.save_fact(new_fact)
        st.success("已写入！")

    if memory.long_term:
        for i, item in enumerate(memory.long_term):
            st.markdown(f"`[{i}]` {item['fact']}")
    else:
        st.caption("暂无长期记忆")

    st.divider()
    if st.button("🗑️ 清空短期记忆（开始新对话）"):
        memory.clear_short_term()
        st.session_state.chat_log.clear()
        st.rerun()

# == 主对话区 ==
for msg in st.session_state.chat_log:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

user_input = st.chat_input("输入消息…")
if user_input:
    if not cfg.API_KEY:
        st.error("请在 .env 文件中设置 API_KEY")
        st.stop()

    with st.chat_message("user"):
        st.write(user_input)

    # 组装消息（短期 + 长期记忆 -> Prompt）
    messages = memory.build_messages(
        query=user_input,
        system_prompt=cfg.SYSTEM_PROMPT,
    )

    # BASE_URL 支持任意兼容 OpenAI 接口的服务
    client = OpenAI(api_key=cfg.API_KEY, base_url=cfg.BASE_URL)
    with st.chat_message("assistant"):
        with st.spinner("思考中…"):
            response = client.chat.completions.create(
                model=model,
                messages=messages,
            )
        reply = response.choices[0].message.content
        st.write(reply)

    memory.add_message("user", user_input)
    memory.add_message("assistant", reply)
    st.session_state.chat_log.append({"role": "user",      "content": user_input})
    st.session_state.chat_log.append({"role": "assistant", "content": reply})

# == Debug：当前记忆状态 ==
with st.expander("🔍 当前记忆状态（Debug）"):
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("短期记忆（对话窗口）")
        st.json(memory.short_term)
    with col2:
        st.subheader("长期记忆（事实列表）")
        st.json(memory.long_term)
