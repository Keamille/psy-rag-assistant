# RAG 评测集

`qa_set.jsonl` 每行一条评测样本，字段与开发文档 12.4 一致：

```json
{"id": "q-001",
 "question": "什么是自动思维？",
 "expected_points": ["自动涌现", "未经审视", "影响情绪"],
 "expected_source_files": ["cbt-01-自动思维.md"],
 "answerable": true,
 "risk_level": "safe"}
```

## 当前状态

当前只有少量样例（10 条，其中 1 条为拒答用例），作用是锁定数据格式与评测脚本的输入契约。
按开发文档 12.4 的要求，**正式评测前需要扩充到 30–50 条**，
覆盖 `backend/app/data/base_knowledge/` 下全部 12 个主题，
并包含 8–10 条 `answerable: false` 的拒答用例；
配套的评测脚本（`eval_rag.py`，输出 Hit@5 与 MRR）也尚未落地。

评测指标与目标（Hit@5 ≥ 0.85、MRR ≥ 0.70、引用正确率 ≥ 0.80、
忠实度 ≥ 0.85、拒答正确率 ≥ 0.90、幻觉引用率 ≤ 0.05）见开发文档 12.4。

