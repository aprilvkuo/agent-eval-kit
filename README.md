# Agent Eval Kit

一个代码库完成两件事：

1. **Agent Runner**：让模型在任务自带的 Mock 环境中调用工具、查询数据并修改状态。
2. **Evaluator**：根据 `output.target_state`、逐项覆盖率和工具合法性进行评分。

## 快速开始

要求 Python 3.9+。

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

先用 Oracle 验证任务、Mock 环境和评分器：

```bash
agent-eval benchmark \
  --tasks examples/agent_eval/education_graduation_audit.jsonl \
  --output-dir runs/oracle \
  --agent oracle \
  --trials-per-task 3
```

正常结果应为 `pass_rate=1.0`。

## 使用真实模型

本工具调用 OpenAI-compatible `/v1/chat/completions`，可连接 LiteLLM、vLLM 等服务。

复制配置模板并填入自己的值：

```bash
cp .env.example .env
set -a
source .env
set +a
```

`.env` 已加入忽略规则，不会提交到 Git。只需要三个配置：

| 配置 | 含义 |
|---|---|
| `ANTHROPIC_AUTH_TOKEN` | API Token |
| `ANTHROPIC_BASE_URL` | 服务根地址；没有路径时自动补 `/v1` |
| `ANTHROPIC_MODEL` | 模型名称 |

运行：

```bash
agent-eval benchmark \
  --tasks examples/agent_eval/education_graduation_audit.jsonl \
  --output-dir runs/model \
  --agent openai \
  --trials-per-task 3 \
  --temperature 0
```

也可以显式传入 `--model`、`--base-url` 和 `--api-key-env`；命令参数优先于默认环境变量。

## 输出文件

每次 `benchmark` 会在指定目录生成：

| 文件 | 内容 |
|---|---|
| `trials.jsonl` | 每次运行的 transcript、工具结果和 final state |
| `evaluations.jsonl` | 每次运行的评分明细和失败原因 |
| `summary.json` | 通过率、平均分、`pass@k` 和稳定性汇总 |

## 评分

```text
score = 70% × target state 字段准确率
      + 20% × 待核查项覆盖率
      + 10% × 工具调用合法率
```

严格通过要求：trial 正常完成、`output.target_state` 完全满足、逐项覆盖率为 100%，且没有非法工具调用。

## 代码结构

```text
scripts/agent_eval/
  agents.py       模型与 Oracle 策略
  environment.py  Mock 数据库、工具和状态变化
  runner.py       Trial 执行与 transcript 记录
  evaluator.py    单条评分与汇总
  cli.py          run / evaluate / benchmark 命令
examples/agent_eval/  示例任务
tests/                自动化测试
```

详细说明见 [docs/agent_runner_evaluator.md](docs/agent_runner_evaluator.md)。

## 开发验证

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

