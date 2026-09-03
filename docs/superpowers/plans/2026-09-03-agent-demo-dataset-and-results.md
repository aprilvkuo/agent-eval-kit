# Agent Demo Dataset And Results Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将修复后的 20 条 Agent Demo 测试数据、Schema 回归检查和 2026-09-03 模型评测结论纳入公开代码库，并更新 README 后推送到 GitHub。

**Architecture:** 测试集放在现有 `examples/agent_eval/`，继续使用仓库约定的 JSONL 接口结构；自动化测试只验证公开 Schema 契约和数据规模，不固化业务结果。模型运行的汇总结论放入独立文档，README 只保留入口、最短运行命令和关键限制。

**Tech Stack:** JSONL、Python `unittest`、Markdown、Git。

## Global Constraints

- 顶层字段严格为 `id`、`type`、`abilities`、`input`、`output`、`source`、`extra`。
- `target_state` 只能位于 `output.target_state`，顶层不得出现 `target_state`。
- 提交前不得包含 API Token 或真实认证配置。
- 不提交 `runs/` 中的大体积临时评测产物，只提交可复现命令和汇总结论。

---

### Task 1: 纳入修复后的测试集和 Schema 回归测试

**Files:**
- Create: `examples/agent_eval/agent_demo.jsonl`
- Create: `tests/test_agent_demo_dataset.py`

**Interfaces:**
- Consumes: `/Users/4paradigm/Desktop/agent_demo.jsonl`，共 20 条 JSONL 记录。
- Produces: 仓库内可直接传给 `agent-eval benchmark --tasks` 的测试集。

- [ ] **Step 1: 写入失败的 Schema 回归测试**

```python
def test_agent_demo_dataset_uses_output_target_state(self):
    self.assertEqual(20, len(self.rows))
    for row in self.rows:
        self.assertEqual(
            ["id", "type", "abilities", "input", "output", "source", "extra"],
            list(row),
        )
        self.assertNotIn("target_state", row)
        self.assertIsInstance(row["output"]["target_state"], dict)
```

- [ ] **Step 2: 运行测试并确认缺少数据文件时失败**

Run: `python3 -m unittest tests.test_agent_demo_dataset -v`

Expected: FAIL，提示 `examples/agent_eval/agent_demo.jsonl` 不存在。

- [ ] **Step 3: 复制已修复数据到示例目录**

Run: `cp '/Users/4paradigm/Desktop/agent_demo.jsonl' examples/agent_eval/agent_demo.jsonl`

- [ ] **Step 4: 运行测试并确认通过**

Run: `python3 -m unittest tests.test_agent_demo_dataset -v`

Expected: 通过，20 条记录均符合 `output.target_state` 契约。

### Task 2: 更新 README 和评测报告

**Files:**
- Modify: `README.md`
- Create: `docs/agent_demo_benchmark_2026-09-03.md`

**Interfaces:**
- Consumes: `runs/agent_demo_20260903/*/summary.json` 与逐条评估结果。
- Produces: 可复现命令、Qwen 有效结果、DeepSeek `401` 阻塞原因、Oracle 基线问题清单。

- [ ] **Step 1: 编写评测报告**

报告必须包含：数据规模和行业分布；`qwen3.8-27b-fp8` 的 `6/20`、平均分 `0.8655`；`deepseek-v4-flash-0731` 的 20 次 `401 Unauthorized`；Oracle 的 `11/20`；9 条 Oracle 失败意味着当前数据仍有 Mock/Oracle 契约问题。

- [ ] **Step 2: 更新 README**

README 增加 `agent_demo.jsonl` 的说明、最短 Oracle/真实模型运行命令，以及评测报告链接；明确不要把 `401` 结果解释为 DeepSeek 模型能力分数。

- [ ] **Step 3: 校验文档中的文件链接和关键数字**

Run: `rg -n 'agent_demo.jsonl|0.8655|401 Unauthorized|11/20' README.md docs/agent_demo_benchmark_2026-09-03.md`

Expected: 数据入口、结果数字和限制均可检索到。

### Task 3: 完整验证并推送

**Files:**
- Verify: repository working tree and GitHub `main`

**Interfaces:**
- Consumes: Task 1 和 Task 2 的全部变更。
- Produces: 已推送且本地/远端 HEAD 一致的公开代码库。

- [ ] **Step 1: 运行完整测试**

Run: `python3 -m unittest discover -s tests -p 'test_*.py'`

Expected: 所有测试通过。

- [ ] **Step 2: 检查格式、构建和敏感信息**

Run: `git diff --check && node --check scripts/agent_eval/web/static/app.js && python3 -m build`

Expected: 全部退出码为 0；Git 历史和待提交文件中没有 token 形式的值。

- [ ] **Step 3: 提交并推送**

```bash
git add README.md docs examples/agent_eval/agent_demo.jsonl tests/test_agent_demo_dataset.py
git commit -m "docs: add agent demo dataset and benchmark results"
git push origin main
```

- [ ] **Step 4: 回读远端状态**

Run: `git ls-remote origin refs/heads/main`

Expected: 远端 `main` 与本地 `HEAD` 相同，工作区干净。
