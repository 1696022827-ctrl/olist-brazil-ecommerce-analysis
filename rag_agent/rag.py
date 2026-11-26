# -*- coding: utf-8 -*-
"""
RAG 知识库问答 Agent —— 核心模块
==================================
链路：文档加载 → 文本切分 → 向量化(Embedding) → FAISS 向量库 → 检索 Top-K → Prompt 拼接 → qwen 生成

设计要点：
  1. 向量化用 DashScope text-embedding-v3（走 OpenAI 兼容接口，与 qwen-plus 同一套 .env）
  2. 向量库用 FAISS，本地持久化到 data/index，避免每次重启都重新向量化
  3. 检索后做相似度阈值过滤，低相关片段不塞进上下文，减少幻觉
  4. 生成时严格约束「只基于检索内容回答，找不到就明说」，并附上来源文件名
  5. 支持多轮：最近 3 轮问答注入提示词，理解指代
"""

import os
import time
from dotenv import load_dotenv

load_dotenv()  # 读取同目录 .env（OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL）

# 支持 Streamlit Cloud Secrets（云端无 .env 文件时从 st.secrets 读）
try:
    import streamlit as st
    if hasattr(st, "secrets") and "OPENAI_API_KEY" in st.secrets:
        os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
        os.environ["OPENAI_BASE_URL"] = st.secrets.get(
            "OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        os.environ["OPENAI_MODEL"] = st.secrets.get("OPENAI_MODEL", "qwen-plus")
except Exception:
    pass

# dashscope SDK 读 DASHSCOPE_API_KEY；.env 里写的是 OPENAI_API_KEY（同一个百炼 key），映射过去
os.environ.setdefault("DASHSCOPE_API_KEY", os.getenv("OPENAI_API_KEY", ""))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "data", "docs")
INDEX_DIR = os.path.join(BASE_DIR, "data", "index")

# 检索与切分参数
CHUNK_SIZE = 500       # 每个文本块 500 字符
CHUNK_OVERLAP = 50     # 块之间重叠 50 字符，保留上下文连贯
TOP_K = 4              # 检索最相关的 4 个片段
SIM_THRESHOLD = 0.35   # 相似度阈值（归一化后），低于此值视为不相关
EMBED_MODEL = "text-embedding-v3"
MAX_HISTORY_ROUNDS = 3


def get_llm():
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "qwen-plus"),
        temperature=0,
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
        timeout=30,
        max_retries=1,
    )


def get_embeddings():
    from langchain_community.embeddings import DashScopeEmbeddings
    # text-embedding-v3：1024 维，支持中英文，百炼免费额度内
    return DashScopeEmbeddings(model=EMBED_MODEL)


# ---------------- 1. 文档加载 ----------------
def load_documents(docs_dir: str = DOCS_DIR):
    """加载 docs_dir 下所有 .md / .txt / .pdf 文件"""
    from langchain_community.document_loaders import DirectoryLoader, TextLoader
    from langchain_community.document_loaders import PyPDFLoader
    from langchain_core.documents import Document

    docs = []
    if not os.path.isdir(docs_dir):
        return docs

    # 文本类（md / txt）用 TextLoader，按扩展名分别加载（pathlib 不支持花括号展开）
    for ext in ("md", "txt"):
        loader = DirectoryLoader(
            docs_dir,
            glob=f"**/*.{ext}",
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"},
            show_progress=False,
            recursive=True,
        )
        docs.extend(loader.load())

    # PDF 单独处理（pypdf）
    for root, _, files in os.walk(docs_dir):
        for fn in files:
            if fn.lower().endswith(".pdf"):
                path = os.path.join(root, fn)
                try:
                    docs.extend(PyPDFLoader(path).load())
                except Exception as e:
                    print(f"[警告] 跳过 PDF {fn}: {e}")

    # 给每个文档补上 source 元数据（用于回答时标注来源）
    for d in docs:
        src = d.metadata.get("source", "")
        d.metadata["source"] = os.path.basename(src) if src else "未知来源"
    return docs


# ---------------- 2. 文本切分 ----------------
def split_documents(docs):
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n## ", "\n### ", "\n", "。", "！", "？", " ", ""],
    )
    return splitter.split_documents(docs)


# ---------------- 3. 构建 / 加载 FAISS 索引 ----------------
def build_index(docs_dir: str = DOCS_DIR, index_dir: str = INDEX_DIR):
    """从原始文档构建 FAISS 向量库并持久化"""
    from langchain_community.vectorstores import FAISS

    docs = load_documents(docs_dir)
    if not docs:
        raise RuntimeError(f"未在 {docs_dir} 找到任何文档")
    chunks = split_documents(docs)
    print(f"文档 {len(docs)} 篇 → 切分后 {len(chunks)} 个块，开始向量化…")

    db = FAISS.from_documents(chunks, get_embeddings())
    os.makedirs(index_dir, exist_ok=True)
    db.save_local(index_dir)
    print(f"索引已保存到 {index_dir}")
    return db


def load_index(index_dir: str = INDEX_DIR):
    """加载已持久化的 FAISS 索引；不存在则现场构建"""
    from langchain_community.vectorstores import FAISS
    if not (os.path.exists(os.path.join(index_dir, "index.faiss"))):
        print("索引不存在，正在构建…")
        return build_index()
    db = FAISS.load_local(index_dir, get_embeddings(), allow_dangerous_deserialization=True)
    return db


# ---------------- 4. 检索 ----------------
def _normalize_score(l2: float) -> float:
    """FAISS 默认返回 L2 距离，转成 0~1 的相似度（越大越相关）"""
    return float(1.0 / (1.0 + l2))


def retrieve(db, query: str, k: int = TOP_K):
    """检索 Top-K 相关片段，过滤低于阈值的结果"""
    results = db.similarity_search_with_score(query, k=k)
    retrieved = []
    for doc, score in results:
        sim = _normalize_score(score)
        if sim >= SIM_THRESHOLD:
            retrieved.append((doc, sim))
    # 按相似度降序
    retrieved.sort(key=lambda x: x[1], reverse=True)
    return retrieved


# ---------------- 5. 生成回答 ----------------
RAG_PROMPT = """你是云效科技的内部知识库助手。请严格根据下面提供的「参考资料」回答用户问题。

规则：
1. 只能使用参考资料里的信息，不要编造资料中没有的内容。
2. 如果参考资料里没有相关信息，直接回答「根据现有知识库，暂时没有找到相关信息」，不要猜测。
3. 回答简洁准确，关键数字保留。涉及多条规则时用分点列出。
4. 在回答末尾用「来源：xxx.md」标注参考资料来自哪个文件，多个用顿号分隔。

参考资料：
{context}

{history}
用户问题：{question}
"""


def _build_history_text(history) -> str:
    if not history:
        return ""
    lines = []
    for item in history[-MAX_HISTORY_ROUNDS:]:
        lines.append(f"用户：{item.get('q','')}\n助手：{item.get('a','')}")
    return "此前对话（仅用于理解指代）：\n" + "\n".join(lines) + "\n\n"


def answer(db, question: str, history=None):
    """
    主入口：检索 + 生成。
    返回 dict: {answer, sources, retrieved}
      sources: 来源文件名列表
      retrieved: [(片段内容, 相似度), ...] 供界面展示
    """
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser

    retrieved = retrieve(db, question)
    retrieved = retrieved[:TOP_K]

    retrieved_payload = []  # 给界面展示的干净数据
    context_parts = []
    sources = []
    for i, (doc, sim) in enumerate(retrieved, 1):
        text = doc.page_content.strip().replace("\n", " ")
        src = doc.metadata.get("source", "未知")
        sources.append(src)
        context_parts.append(f"[资料{i}]（来源：{src}）{text}")
        retrieved_payload.append({"text": text, "source": src, "score": round(sim, 3)})

    # 无相关资料：直接走兜底，不调用大模型（省钱、避免幻觉）
    if not context_parts:
        return {
            "answer": "根据现有知识库，暂时没有找到相关信息。你可以换个问法，或在「文档管理」里补充相关资料后重建索引。",
            "sources": [],
            "retrieved": [],
        }

    prompt = ChatPromptTemplate.from_template(RAG_PROMPT)
    chain = prompt | get_llm() | StrOutputParser()

    t0 = time.time()
    try:
        out = chain.invoke({
            "context": "\n\n".join(context_parts),
            "history": _build_history_text(history or []),
            "question": question,
        })
    except Exception as e:
        msg = str(e)
        if "timed out" in msg.lower() or "timeout" in msg.lower():
            out = "模型响应超时了，请稍后重试或把问题拆小一点。"
        elif "429" in msg or "quota" in msg.lower() or "budget" in msg.lower():
            out = "大模型账户额度已用尽（429），请到百炼控制台调整预算或领取免费额度。"
        else:
            out = f"生成回答时出错：{msg[:150]}"
    elapsed = round(time.time() - t0, 2)

    return {
        "answer": out.strip(),
        "sources": list(dict.fromkeys(sources)),  # 去重保序
        "retrieved": retrieved_payload,
        "elapsed": elapsed,
    }


if __name__ == "__main__":
    db = load_index()
    print("知识库已就绪，输入问题开始问答（quit 退出）\n")
    history = []
    while True:
        q = input("你: ").strip()
        if q.lower() in ("quit", "exit", "退出"):
            break
        if not q:
            continue
        res = answer(db, q, history)
        print(f"助手: {res['answer']}")
        print(f"  （耗时 {res.get('elapsed','?')}s，来源 {res['sources']}）")
        history.append({"q": q, "a": res["answer"]})
