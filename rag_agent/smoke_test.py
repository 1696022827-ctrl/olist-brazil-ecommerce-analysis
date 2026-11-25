# -*- coding: utf-8 -*-
"""非交互式烟测：建索引 + 跑 5 个问题，验证 RAG 全链路"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from rag import build_index, answer

db = build_index()
print("=" * 60)

questions = [
    "入职满4年有多少天年假？",
    "报销超过2000元需要谁审批？",
    "数据看板Pro支持多少种图表？数据刷新最快多久一次？",
    "API免费版每天能调用多少次？超限返回什么状态码？",
    "公司服务器部署在哪几个城市？深圳的RPO是多少？",
    "今天午饭吃什么？",  # 兜底题：知识库没有，应该答"未找到"
]
for q in questions:
    res = answer(db, q)
    print(f"\nQ: {q}")
    print(f"A: {res['answer']}")
    print(f"   耗时 {res.get('elapsed','?')}s | 来源 {res['sources']} | 命中片段 {len(res['retrieved'])}")
