# Agent Eval Kit

一个代码库完成三件事：

1. **Agent Runner**：让模型在任务自带的 Mock 环境中调用工具、查询数据并修改状态。
2. **Evaluator**：根据 `output.target_state`、逐项覆盖率和工具合法性进行评分。
3. **Web Dashboard**：管理 JSONL 测试集、运行模型，并查看评分、模型输出和每一步状态变化。

## 网页版（推荐）

安装网页依赖并启动：

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[web]'
agent-eval web
```

浏览器打开 `http://127.0.0.1:8765`。网页支持：

- 导入、查看和删除 JSONL 测试集；
- 从当前 LiteLLM `/v1/models` 下拉选择模型，运行 Oracle 基准或 OpenAI-compatible 真实模型；
- 查看通过率、平均分、`pass@k` 和平均工具调用数；
- 下钻每个 Trial，查看 Task 输入、完整 Model Request/Response、每轮 Token 与耗时、函数参数、Mock 返回值、调用前后状态、Outcome 和 Grade。

测试集、运行和 Trial 保存在本地 `workspace/dashboard.db`。API Token 只从本地环境变量读取，不会写入网页或数据库；服务默认只监听 `127.0.0.1`。

如果模型服务使用 Tailscale 地址，并且本机配置了 HTTP 代理，需要把服务主机加入 `NO_PROXY`，避免请求被代理为 `502`：

```bash
export NO_PROXY="127.0.0.1,localhost,<your-host>.ts.net"
export no_proxy="$NO_PROXY"
```

## 命令行版

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
  cli.py          run / evaluate / benchmark / web 命令
  web/            FastAPI、SQLite 与 Dashboard 静态页面
examples/agent_eval/  示例任务
tests/                自动化测试
```

详细说明见 [docs/agent_runner_evaluator.md](docs/agent_runner_evaluator.md)。

## 开发验证

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```
