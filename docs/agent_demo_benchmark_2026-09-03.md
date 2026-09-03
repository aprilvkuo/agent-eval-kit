# Agent Demo 基准结果（2026-09-03）

## 测试范围

- 数据文件：`examples/agent_eval/agent_demo.jsonl`
- 任务数：20
- 行业分布：教育、金融、医疗、通信各 5 条
- Trial：每个任务、每个模型运行 1 次
- 参数：`temperature=0`，工具步数上限取任务 `extra.max_autonomous_steps` 的上限
- 评分：目标状态准确率 70%、逐项覆盖率 20%、工具合法率 10%

测试数据已经迁移到正式接口结构，`target_state` 只位于 `output.target_state`。

## 汇总结果

| Agent / 模型 | 有效状态 | 通过数 | 通过率 | 平均分 | 平均工具调用 |
|---|---|---:|---:|---:|---:|
| Oracle | 20 条完成 | 11/20 | 55% | 0.900627 | 7.05 |
| `qwen3.8-27b-fp8` | 17 条完成，3 条达到步数上限 | 6/20 | 30% | 0.8655 | 6.9 |
| `deepseek-v4-flash-0731` | 20 条均为上游认证错误 | 不适用 | 不适用 | 不适用 | 0 |

`deepseek-v4-flash-0731` 虽然能从 LiteLLM `/v1/models` 查询到，但 20 次实际请求全部返回 `401 Unauthorized`。这说明 LiteLLM 对应 Model Group 的上游凭据不可用；本轮不能得到有效的 DeepSeek 模型能力分数。

## Qwen 结果

### 分行业

| 行业 | 通过数 | 通过率 | 平均分 |
|---|---:|---:|---:|
| 教育 | 1/5 | 20% | 0.883333 |
| 金融 | 2/5 | 40% | 0.778667 |
| 医疗 | 0/5 | 0% | 0.853333 |
| 通信 | 3/5 | 60% | 0.946667 |

### 主要失败项

失败类型可能在同一个 Trial 中重叠：

- 14 条存在 `target_state_mismatch`；其中常见字段为 `hold_reason`、`related_queried`、`log_queried`。
- 3 条 `trial_not_completed`，均达到工具步数上限。
- 3 条存在 `invalid_tool_calls`。
- 1 条存在 `incomplete_item_coverage`。

本轮共使用 169,687 Tokens，其中 Prompt 161,238、Completion 8,449；平均每个 Trial 用时约 16.65 秒。

## Oracle 基线发现的数据问题

Oracle 只通过 11/20，因此当前原始通过率不能完全归因于模型能力。9 条 Oracle 失败如下：

| Task ID | 主要问题 |
|---|---|
| `agent_education_014593` | `query_related` 引用的关联实体不存在 |
| `agent_finance_029257` | 多个金融查询/审核工具在 Mock 环境中未实现 |
| `agent_finance_018290` | Oracle 轨迹遗漏“异常溯源”核查项 |
| `agent_finance_026531` | `query_account`、`query_counterparty`、`fx_convert` 未实现 |
| `agent_medical_071483` | `query_related` 引用的关联实体不存在 |
| `agent_medical_011396` | 关联实体不存在，同时 Oracle 轨迹遗漏核查项 |
| `agent_medical_077398` | `query_related` 引用的关联实体不存在 |
| `agent_telecom_012281` | Oracle 轨迹遗漏“原因定位一/二” |
| `agent_telecom_028658` | 关联实体不存在，同时 Oracle 轨迹遗漏“携号转网” |

在 Oracle 能通过的 11 条任务中，Qwen 通过 5 条，即 45.5%。Qwen 另外通过了 `agent_finance_018290`，说明该任务本身可由模型完成，但 Oracle 参考轨迹不完整。

## 复现命令

先运行 Oracle：

```bash
agent-eval benchmark \
  --tasks examples/agent_eval/agent_demo.jsonl \
  --output-dir runs/agent-demo/oracle \
  --agent oracle
```

再运行 OpenAI-compatible 模型：

```bash
agent-eval benchmark \
  --tasks examples/agent_eval/agent_demo.jsonl \
  --output-dir runs/agent-demo/qwen3.8-27b-fp8 \
  --agent openai \
  --model qwen3.8-27b-fp8 \
  --temperature 0
```

API 地址和 Token 应通过本地环境变量提供，不要提交到代码库。

## 结论

当前可以确认 Qwen 能正常完成工具调用和状态更新，但还不能用 30% 作为纯模型能力结论。建议先修复上述 9 条 Oracle 基线失败，再对两个模型各运行至少 3 个 Trial，计算 `pass@k` 和 `pass_all_k`。
