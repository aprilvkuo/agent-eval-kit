# Agent Runner 与评估脚本

## 1. 功能

本工具把两个模块封装在同一个 `agent-eval` 命令中：

| 模块 | 作用 | 主要输出 |
|---|---|---|
| Agent Runner | 让 Agent 在任务自带的 mock 环境中调用函数、查询数据并更新状态 | trial、transcript、final state |
| Evaluator | 根据目标状态和实际工具轨迹评估任务结果 | 单条评分、通过率、稳定性指标 |

Runner 不会把 `output` 或 `extra.hidden` 提供给真实模型。真实模型只能看到：

- `input.prompt`
- `input.files`
- `input.initial_state`
- `input.tools`
- 每次工具调用的返回结果

## 2. Web Dashboard

安装并启动本地网页：

```bash
python3 -m pip install -e '.[web]'
agent-eval web --data-dir workspace --host 127.0.0.1 --port 8765
```

打开 `http://127.0.0.1:8765` 后，可以导入和删除测试集、运行 Oracle 或真实模型、查看汇总指标，并下钻每个 Trial 的模型最终回答、工具参数、工具返回值、`state_before/state_after` 差异和评分诊断。

网页数据保存在 `workspace/dashboard.db`。Token 仍只从 `ANTHROPIC_AUTH_TOKEN` 或 `OPENAI_API_KEY` 读取，不通过 Web API 传输，也不写入 SQLite。服务默认只监听本机。

## 3. 命令行快速开始

安装：

```bash
python3 -m pip install -e .
```

推荐直接使用 `benchmark`，一次完成运行和评分：

```bash
agent-eval benchmark \
  --tasks examples/agent_eval/education_graduation_audit.jsonl \
  --output-dir runs/oracle \
  --agent oracle \
  --trials-per-task 3
```

## 4. Mock 环境

每次 trial 都创建独立的 `MockEnvironment`：

| 数据 | 来源 | 用途 |
|---|---|---|
| 初始状态 | `input.initial_state` | 创建本次运行的状态副本 |
| Mock 数据库 | `extra.hidden.params_state` | 返回案例清单和每项核查结果 |
| 工具前置条件 | `extra.hidden.tool_effects.*.preconditions` | 拒绝不合法的调用顺序 |
| 工具状态变化 | `extra.hidden.tool_effects.*.effects` | 更新本次运行状态 |
| 标准轨迹 | `extra.hidden.oracle_trace` | 验证环境和 grader 可解，不提供给真实模型 |

当前内置通用工具：

```text
verify_identity
query_case
check_item
approve_case
hold_case
query_related
query_log
```

其它简单查询工具可以在 `params_state.tool_responses` 中配置静态返回；需要参数相关逻辑时，在 `MockEnvironment` 中增加对应 handler。

## 5. 先跑 Oracle 基线

Oracle 使用任务中的标准轨迹，作用是确认：

- mock 工具能够正常执行；
- 状态可以到达 `output.target_state`；
- Evaluator 能把正确结果判为通过。

```bash
python3 -m scripts.agent_eval.cli run \
  --tasks examples/agent_eval/education_graduation_audit.jsonl \
  --output runs/oracle_trials.jsonl \
  --agent oracle
```

评估：

```bash
python3 -m scripts.agent_eval.cli evaluate \
  --tasks examples/agent_eval/education_graduation_audit.jsonl \
  --trials runs/oracle_trials.jsonl \
  --details runs/oracle_evaluations.jsonl \
  --summary runs/oracle_summary.json
```

Oracle 应得到 `pass_rate=1.0`。如果 Oracle 失败，优先检查数据、mock 环境或 grader，不应先归因于模型。

## 6. 跑真实模型

### 6.1 OpenAI API

```bash
export OPENAI_API_KEY='<your-api-key>'

python3 -m scripts.agent_eval.cli run \
  --tasks examples/agent_eval/education_graduation_audit.jsonl \
  --output runs/model_trials.jsonl \
  --agent openai \
  --model '<model-name>' \
  --trials-per-task 3 \
  --temperature 0
```

### 6.2 vLLM 或 LiteLLM

只要服务提供 OpenAI-compatible `/v1/chat/completions` 即可：

```bash
export OPENAI_API_KEY='local-key'

python3 -m scripts.agent_eval.cli run \
  --tasks examples/agent_eval/education_graduation_audit.jsonl \
  --output runs/local_model_trials.jsonl \
  --agent openai \
  --model '<served-model-name>' \
  --base-url 'http://127.0.0.1:8000/v1' \
  --trials-per-task 3 \
  --temperature 0
```

如使用自定义 Key 环境变量：

```bash
--api-key-env LITELLM_API_KEY
```

也可直接设置 `ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_BASE_URL`、`ANTHROPIC_MODEL`，然后省略 `--model`、`--base-url` 和 `--api-key-env`。当地址只有主机和端口时，Runner 会自动补 `/v1`。

## 7. Runner 参数

| 参数 | 必填 | 说明 |
|---|---:|---|
| `--tasks` | 是 | 输入任务 JSONL |
| `--output` | 是 | trial 输出 JSONL |
| `--agent` | 是 | `oracle` 或 `openai` |
| `--model` | OpenAI-compatible 必填 | 模型名 |
| `--base-url` | 否 | OpenAI-compatible API 地址 |
| `--api-key-env` | 否 | API Key 环境变量；默认依次读取 `ANTHROPIC_AUTH_TOKEN`、`OPENAI_API_KEY` |
| `--temperature` | 否 | 采样温度，默认 `0` |
| `--max-steps` | 否 | 最大工具调用数；默认取任务步数区间上限 |
| `--trials-per-task` | 否 | 每个任务重复运行次数，默认 `1` |
| `--limit` | 否 | 只运行前 N 条任务 |

## 8. Trial 输出

每条 trial 包含：

```json
{
  "task_id": "agent_education_083811",
  "trial_id": "uuid",
  "agent": "oracle",
  "status": "completed",
  "metadata": {
    "industry": "education",
    "scenario": "edu_graduation_audit",
    "difficulty": "hard"
  },
  "transcript": [],
  "outcome": {
    "final_state": {},
    "final_answer": "",
    "tool_call_count": 7,
    "error": null
  },
  "usage": {},
  "duration_ms": 0,
  "schema_warnings": []
}
```

`transcript` 会保留每轮模型输出、工具名称、参数、返回结果，以及工具调用前后的状态。

## 9. 评分规则

| 指标 | 权重 | 说明 |
|---|---:|---|
| `state_key_accuracy` | 70% | `final_state` 与 `output.target_state` 的字段一致率 |
| `item_coverage` | 20% | 待核查项目被成功逐项检查的比例 |
| `tool_validity` | 10% | 合法工具调用占比 |

总分：

```text
score = 0.7 × state_key_accuracy
      + 0.2 × item_coverage
      + 0.1 × tool_validity
```

严格通过条件：

```text
trial 完成
且 final_state 精确满足 output.target_state
且逐项覆盖率为 100%
且没有非法工具调用
```

## 10. 汇总指标

| 指标 | 含义 |
|---|---|
| `pass_rate` | 所有 trial 中的通过比例 |
| `pass_at_k` | 同一任务运行 K 次，至少一次成功的任务比例 |
| `pass_all_k` | 同一任务运行 K 次，全部成功的任务比例，体现稳定性 |
| `average_score` | 平均综合分 |
| `average_tool_calls` | 平均工具调用次数 |

汇总同时按 `industry`、`scenario`、`difficulty` 分组。

## 11. 推荐运行顺序

1. 先对全部数据运行 Oracle；
2. Oracle 失败的数据先修复任务、环境或 grader；
3. 选择 20～50 条任务跑真实模型，每条至少 3 次；
4. 查看失败 trial 的 transcript，不只看总分；
5. 稳定后再扩大到全量数据。
