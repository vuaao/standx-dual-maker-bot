# StandX Dual-Side Maker Bot

一个面向 `StandX` 永续合约的双边做市机器人。

项目目标很直接：让别人克隆仓库后，能完成安装、配置、自检、测试和试运行，而不是只拿到一个零散脚本。

## 最简单用法

如果你希望别人拉下来后尽量少手工操作，直接用这三步：

```bash
bash scripts/install.sh
bash scripts/setup.sh
bash scripts/run.sh
```

第一步会创建虚拟环境并安装依赖。  
第二步会交互填写私钥、地址和关键参数，并生成 `.env`。  
第三步会执行自检并启动机器人。

## 特性

- 双边限价挂单
- 基于盘口偏移的预警、撤单、重挂
- 订单超时重挂
- `401` 后自动重认证
- 同方向多单清理
- 连续异常熔断
- `stop / pause / cancel-only` 三种熔断动作
- `DRY_RUN` 模式
- 启动自检
- 启动清理历史遗留订单
- 单边挂单次数保护
- 最大偏移保护

## 风险说明

这是高风险交易程序，不是审计过的金融软件。

- 默认先用 `DRY_RUN=true`
- 不要直接使用主钱包
- 不理解参数含义前不要实盘
- 使用本项目造成的任何损失由使用者自行承担

## 快速开始

1. 克隆仓库

```bash
git clone https://github.com/vuaao/standx-dual-maker-bot.git
cd standx-dual-maker-bot
```

2. 安装依赖

```bash
bash scripts/install.sh
```

3. 复制配置模板

```bash
cp .env.example .env
```

4. 建议先用安全配置

```dotenv
DRY_RUN=true
CIRCUIT_BREAKER_ACTION=pause
MAX_CONSECUTIVE_ERRORS=5
MAX_PLACE_ATTEMPTS_PER_SIDE=10
STARTUP_CANCEL_STALE_ORDERS=true
```

5. 先做自检

```bash
python3 standx_bot.py --self-check
```

6. 再开始试运行

```bash
python3 standx_bot.py
```

或者直接：

```bash
bash scripts/install.sh
bash scripts/setup.sh
bash scripts/run.sh
```

## 常用命令

```bash
make install
make setup
make bootstrap
make docker-build
make docker-up
make test
make lint
make self-check
make run
make dry-run
```

如果没有 `make`，可以直接执行：

```bash
python3 -m unittest -v tests/test_standx_runtime_guards.py
python3 -m py_compile standx_bot.py tests/test_standx_runtime_guards.py
python3 standx_bot.py --self-check
python3 standx_bot.py
```

## Docker

构建：

```bash
docker compose build
```

运行：

```bash
docker compose up -d
```

## 项目结构

```text
.
├── .env.example
├── .github/workflows/ci.yml
├── CONTRIBUTING.md
├── Dockerfile
├── docker-compose.yml
├── LICENSE
├── Makefile
├── README.md
├── SECURITY.md
├── docs/DEPLOYMENT.md
├── pyproject.toml
├── requirements.txt
├── scripts/install.sh
├── scripts/run.sh
├── scripts/setup.sh
├── standx_bot.py
└── tests/test_standx_runtime_guards.py
```

## 测试覆盖

当前最小测试主要覆盖：

- 响应结构校验
- `401` 自动重认证
- 冷启动保护
- 仓位查询节流
- 多单清理
- 熔断
- `DRY_RUN`
- 偏移保护
- 挂单次数保护

## 部署与文档

- 部署说明：`docs/DEPLOYMENT.md`
- 安全说明：`SECURITY.md`
- 贡献说明：`CONTRIBUTING.md`

## 后续可扩展方向

- 更完整的 CLI 参数
- 纸面交易回放
- Prometheus 指标
- Telegram / 钉钉告警
- 更细的订单生命周期测试
