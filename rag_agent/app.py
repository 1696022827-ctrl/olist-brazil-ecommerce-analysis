# -*- coding: utf-8 -*-
"""
RAG 知识库问答 Agent —— Streamlit 界面
运行：streamlit run app.py
功能：
  - 对话问答，回答附带来源引用
  - 可展开查看每条命中片段内容与相似度
  - 侧栏：文档列表 / 上传新文档 / 重建索引 / 调节 Top-K 与相似度阈值 / 清空会话
"""
import sys, os, time
sys.stdout.reconfigure(encoding="utf-8")
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rag import load_index, load_documents, build_index, DOCS_DIR, INDEX_DIR, TOP_K, SIM_THRESHOLD

st.set_page_config(page_title="知识库问答 Agent", page_icon="📚", layout="wide")

# ---------- 缓存向量库（只加载一次） ----------
@st.cache_resource(show_spinner="正在加载知识库索引…")
def get_db():
    return load_index()

db = get_db()

# ---------- 侧栏：文档管理 + 参数 ----------
with st.sidebar:
    st.header("⚙️ 设置")

    st.subheader("文档管理")
    doc_files = sorted(os.listdir(DOCS_DIR)) if os.path.isdir(DOCS_DIR) else []
    st.caption(f"当前知识库：{len(doc_files)} 篇文档")
    for fn in doc_files:
        st.text(f"• {fn}")

    uploaded = st.file_uploader("上传新文档（.md / .txt / .pdf）", type=["md", "txt", "pdf"], accept_multiple_files=True)
    if uploaded:
        for f in uploaded:
            with open(os.path.join(DOCS_DIR, f.name), "wb") as out:
                out.write(f.getbuffer())
        st.success(f"已保存 {len(uploaded)} 个文件，点击下方「重建索引」生效")

    if st.button("🔄 重建索引", use_container_width=True):
        with st.spinner("正在切分 + 向量化…"):
            build_index()
            st.cache_resource.clear()
        st.success("索引重建完成！")
        time.sleep(0.5)
        st.rerun()

    st.divider()
    st.subheader("检索参数")
    top_k = st.slider("Top-K（检索片段数）", 1, 8, TOP_K)
    sim_th = st.slider("相似度阈值", 0.0, 0.8, float(SIM_THRESHOLD), 0.05,
                       help="低于此相似度的片段会被过滤，越高越严格")
    st.caption(f"当前：Top-K={top_k}，阈值={sim_th}")

    st.divider()
    if st.button("🗑️ 清空对话", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ---------- 主区：标题 + 对话 ----------
st.title("📚 企业知识库问答 Agent")
st.caption("基于 RAG（检索增强生成）：提问 → 检索相关文档片段 → qwen-plus 生成回答 · 超纲问题会主动说「找不到」")

# 示例问题快捷按钮
examples = [
    "入职满4年有多少天年假？",
    "数据看板Pro支持多少种图表？",
    "API免费版每天能调用多少次？",
    "公司服务器部署在哪几个城市？",
    "今天午饭吃什么？",
]
cols = st.columns(len(examples))
for col, ex in zip(cols, examples):
    if col.button(ex, use_container_width=True):
        st.session_state.pending = ex

if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending" in st.session_state:
    q = st.session_state.pop("pending")
else:
    q = st.chat_input("输入你的问题…")

# 渲染历史
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m.get("sources"):
            with st.expander(f"📎 检索来源（{len(m['sources'])} 个片段）", expanded=False):
                for i, r in enumerate(m["retrieved"], 1):
                    st.markdown(f"**片段 {i}** · `{r['source']}` · 相似度 {r['score']}")
                    st.text(r["text"][:300])

# 处理新问题
if q:
    st.session_state.messages.append({"role": "user", "content": q})
    with st.chat_message("user"):
        st.markdown(q)

    with st.chat_message("assistant"):
        with st.spinner("检索 + 生成中…"):
            history = [{"q": m["content"], "a": ""} for m in st.session_state.messages[:-1] if m["role"] == "assistant"]
            # 重建真实历史（问答对）
            pair_hist = []
            msgs = st.session_state.messages
            for i in range(len(msgs) - 1):
                if msgs[i]["role"] == "user" and i + 1 < len(msgs) and msgs[i + 1]["role"] == "assistant":
                    pair_hist.append({"q": msgs[i]["content"], "a": msgs[i + 1]["content"]})

            # 用侧栏参数临时覆盖 rag 默认值：重新检索
            from rag import retrieve, get_llm, _build_history_text, RAG_PROMPT, _normalize_score, TOP_K as _TK
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_core.output_parsers import StrOutputParser

            results = db.similarity_search_with_score(q, k=top_k)
            retrieved = [(d, _normalize_score(s)) for d, s in results if _normalize_score(s) >= sim_th]
            retrieved.sort(key=lambda x: x[1], reverse=True)

            context_parts, sources, retrieved_payload = [], [], []
            for i, (doc, sim) in enumerate(retrieved[:top_k], 1):
                text = doc.page_content.strip().replace("\n", " ")
                src = doc.metadata.get("source", "未知")
                sources.append(src)
                context_parts.append(f"[资料{i}]（来源：{src}）{text}")
                retrieved_payload.append({"text": text, "source": src, "score": round(sim, 3)})

            if not context_parts:
                answer = "根据现有知识库，暂时没有找到相关信息。你可以换个问法，或在侧栏补充相关文档后重建索引。"
                sources, retrieved_payload = [], []
            else:
                prompt = ChatPromptTemplate.from_template(RAG_PROMPT)
                chain = prompt | get_llm() | StrOutputParser()
                t0 = time.time()
                try:
                    answer = chain.invoke({
                        "context": "\n\n".join(context_parts),
                        "history": _build_history_text(pair_hist[-3:]),
                        "question": q,
                    }).strip()
                except Exception as e:
                    answer = f"生成回答时出错：{str(e)[:120]}"
                elapsed = round(time.time() - t0, 2)
                st.caption(f"⏱️ 耗时 {elapsed}s · 命中 {len(retrieved_payload)} 个片段")

        st.markdown(answer)
        if sources:
            st.markdown(f"**来源：** {'、'.join(dict.fromkeys(sources))}")
            with st.expander(f"📎 检索来源（{len(retrieved_payload)} 个片段）", expanded=False):
                for i, r in enumerate(retrieved_payload, 1):
                    st.markdown(f"**片段 {i}** · `{r['source']}` · 相似度 {r['score']}")
                    st.text(r["text"][:300])

    st.session_state.messages.append({
        "role": "assistant", "content": answer,
        "sources": sources, "retrieved": retrieved_payload,
    })
