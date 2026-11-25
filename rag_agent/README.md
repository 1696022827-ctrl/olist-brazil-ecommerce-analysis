# RAG 企业知识库问答 Agent

基于 **LangChain + FAISS + 通义千问** 构建的企业内部文档问答系统。
上传 Markdown / PDF 文档后自动切分、向量化、存入 FAISS，用户提问时检索相关片段，由 LLM 生成带来源引用的回答；超纲问题主动拒答，不编造知识库外的信息。

## 快速开始

### 1. 安装依赖

```bash
cd rag_agent
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
# Windows PowerShell:
copy .env.example .env

# 然后编辑 .env，填入你的 DashScope API Key
```

推荐用**阿里通义**（免费额度大，国内访问快）：
- 去 https://dashscope.console.aliyun.com/ 开通 DashScope
- 拿到 API Key 后填入 `.env`

### 3. 运行

```bash
# Web 界面（推荐）
streamlit run app.py

# 命令行烟测
python smoke_test.py

# 评测（18 道带标准答案的题，自动判分）
python eval_rag.py
```

## 技术架构

```
文档上传 (Markdown / PDF / TXT)
    ↓
RecursiveCharacterTextSplitter (500 字符 / 重叠 50)
    ↓
text-embedding-v3 向量化 → FAISS 持久化索引
    ↓
用户提问 → 检索 Top-4 片段 → 相似度阈值过滤 (0.35)
    ↓
Prompt 拼接（只基于检索内容 + 标注来源 + 找不到就明说）
    ↓
qwen-plus 生成回答 → Streamlit 展示
```

## 核心设计

| 参数 | 值 | 说明 |
|---|---|---|
| 切分 | 500 字符 / 重叠 50 | RecursiveCharacterTextSplitter |
| 向量模型 | text-embedding-v3 (1024维) | 阿里云 DashScope |
| 检索 | Top-4 | FAISS L2 距离，1/(1+d) 转相似度 |
| 阈值过滤 | 0.35 | 低于阈值的片段不进入上下文 |
| 生成模型 | qwen-plus | 走 OpenAI 兼容接口 |
| 多轮 | 最近 3 轮 | 注入 prompt 理解指代 |

### 防幻觉三层机制

1. **检索侧**：相似度 < 0.35 的片段不进入上下文
2. **Prompt 约束**：「只基于检索内容回答，找不到就明说」
3. **无命中不调 LLM**：检索为空时直接返回「未找到」，不调 LLM 避免编造

### 工程细节

- API 超时 30 秒 / 单轮 90 秒 / 最多 10 步
- 异常统一转为中文友好提示
- 索引持久化到 `data/index/`，重启不重新向量化
- 新增文档可一键重建索引

## 评测结果

自建 18 道带标准答案的评测集（含 1 道超纲拒答题），关键字匹配自动判分：

| 指标 | 结果 |
|---|---|
| 检索命中 (hit@k) | 18/18 |
| 答案准确率 | 18/18 |
| 平均响应 | 1.3 秒 |
| 超纲拒答 | 正确拒答，不编造 |

> 评测集为自构建，覆盖年假、报销、试用期、产品、API、远程办公、数据安全、基础设施、SLA 等 10 篇文档，不代表泛化能力。明细见 `eval_result.csv`。

## 项目结构

```
rag_agent/
├── data/
│   ├── docs/              # 10 篇 Markdown 语料（公司制度文档）
│   └── index/             # FAISS 持久化索引
├── rag.py                 # 核心模块（切分/向量化/检索/生成）
├── app.py                 # Streamlit 界面
├── eval_rag.py            # 18 题评测脚本
├── smoke_test.py          # 烟测脚本
├── generate_corpus.py     # 语料生成脚本
├── eval_result.csv        # 评测明细
├── .env.example           # API Key 配置模板
├── requirements.txt       # Python 依赖
└── README.md
```
