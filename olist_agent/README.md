# Olist 电商数据智能分析 Agent

基于 **LangChain（ReAct）+ Streamlit** 构建的电商数据分析 Agent。
用户用自然语言提问，Agent 自动生成并执行 Pandas 代码，支持数据查询和图表生成。
支持多轮对话：最近 3 轮问答会作为上下文注入提示词，可直接追问「那这个月呢」。

## 快速开始

### 1. 安装依赖

```bash
cd olist_agent
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
# Windows PowerShell:
copy .env.example .env

# 然后编辑 .env，填入你的 API Key
```

推荐用**阿里通义**（免费额度大，国内访问快）：
- 去 https://dashscope.console.aliyun.com/ 开通 DashScope
- 拿到 API Key 后填入 `.env`
- `OPENAI_BASE_URL` 保持默认的 `https://dashscope.aliyuncs.com/compatible-mode/v1`
- `OPENAI_MODEL` 可以用 `qwen-plus`（推荐）或 `qwen-turbo`（更快更便宜）

也支持**任何 OpenAI 兼容接口**（硅基流动、百度千帆等），改 `.env` 里的三行就行。

### 3. 运行

```bash
# Web 界面（推荐）
streamlit run app.py

# 命令行测试
python agent.py

# 准确率评测（20 道带标准答案的题，自动判分并写入 eval_result.csv）
python eval_agent.py
```

打开浏览器看到 Streamlit 界面就成功了！

## 项目结构

```
olist_agent/
├── data/              # 4 张 CSV 数据表（从 Olist 分析项目复制来的）
│   ├── clean_wide.csv
│   ├── rfm_result.csv
│   ├── category_sales_stats.csv
│   └── category_review_stats.csv
├── agent.py           # LangChain Agent 核心逻辑
├── app.py             # Streamlit 界面
├── eval_agent.py      # 20 题准确率评测脚本
├── eval_result.csv    # 评测明细（运行后生成）
├── .env.example       # API Key 配置模板
├── requirements.txt   # Python 依赖
└── README.md
```

## 技术架构

```
用户提问 (自然语言)
    ↓
LangChain Pandas Agent (ReAct 架构)
    ↓
    LLM 思考 → 选择工具 → 生成 Pandas 代码
    ↓
    execute() 执行代码 → 得到结果 / 图表
    ↓
    LLM 组织自然语言回答
    ↓
Streamlit 界面展示
```

## 面试准备

这个项目可以串起来讲一个完整的故事：

> "我先用传统方法（SQL + Pandas + PowerBI）做了 Olist 电商分析，
> 然后发现运营每次要看数据都要手动跑代码太慢了，
> 于是用 LangChain 做了一个 Agent，让运营直接用自然语言问数据，
> 底层自动生成 Pandas 代码执行，前端用 Streamlit 做了对话界面。
> 这样既复用了之前分析好的数据结构，又实现了从 '手动分析' 到 '智能问答' 的升级。"
