# StandX Dual-Side Maker Bot

一个面向 `StandX` 永续合约的双边做市机器人项目。

这个仓库不是“只有一个脚本”，而是一个可发布、可测试、可部署、可被别人直接使用的最小开源项目。

## 适合谁

适合希望做下面这些事的人：

- 直接本地运行
- 用 `DRY_RUN` 先验证策略行为
- 部署到 Linux 服务器长期运行
- Fork 后继续扩展自己的做市策略

## 当前项目包含

- 主程序：`standx_bot.py`
- 环境变量模板：`.env.example`
- 依赖清单：`requirements.txt`
- Python 项目元数据：`pyproject.toml`
- Docker 运行支持：`Dockerfile`
- CI：`.github/workflows/ci.yml`
- 部署文档：`docs/DEPLOYMENT.md`
- 最小单元测试：`tests/test_standx_runtime_guards.py`

## 主要能力

- 双边限价挂单
- 基于盘口偏移的预警、撤单、重挂
- 订单超时重挂
- `401` 后自动重认证
- 同方向多单清理
- 连续异常熔断
- `stop / pause / cancel-only` 三种熔断动作
- `DRY_RUN` 模式
- 启动自检
- 启动时清理历史遗留订单
- 单边挂单次数上限保护
- 最大偏移保护

## 风险说明

这是高风险交易程序，不是审计过的金融软件。

- 默认建议先用 `DRY_RUN=true`
- 不要直接用主钱包
- 不要在不理解参数含义的情况下实盘
- 使用本项目造成的任何损失由使用者自行承担

## 快速开始

1. 克隆仓库

```bash
git clone https://github.com/<your-user-or-org>/standx-dual-maker-bot.git
cd standx-dual-maker-bot
```

2. 创建虚拟环境并安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. 复制配置模板

```bash
cp .env.example .env
```

4. 先用安全配置

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

## 常用命令

```bash
make install
make test
make lint
make self-check
make run
make dry-run
```

如果你的环境没有 `make`，也可以直接执行：

```bash
python3 -m unittest -v tests/test_standx_runtime_guards.py
python3 -m py_compile standx_bot.py tests/test_standx_runtime_guards.py
python3 standx_bot.py --self-check
python3 standx_bot.py
```

## Docker 运行

构建镜像：

```bash
docker build -t standx-dual-maker-bot .
```

运行容器：

```bash
docker run --rm --env-file .env standx-dual-maker-bot
```

## GitHub 开源发布流程

1. 确认以下文件不会提交：
   - `.env`
   - `bot.log`
   - 本地调试目录
   - 任何真实私钥或真实日志

2. 初始化仓库并提交：

```bash
git init
git add .
git commit -m "Initial open source release"
git branch -M main
```

3. 在 GitHub 创建公开仓库：
   - 仓库名建议：`standx-dual-maker-bot`
   - 不要勾选自动生成 `README`、`.gitignore`、`LICENSE`

4. 推送：

```bash
git remote add origin https://github.com/<your-user-or-org>/standx-dual-maker-bot.git
git push -u origin main
```

## 给别人使用时的建议

如果你要让别人直接用，至少要做到：

1. 保留 `.env.example`
2. 保留 `README.md`
3. 保留 `docs/DEPLOYMENT.md`
4. 保留测试和 CI
5. 在仓库首页明确写风险说明

## 目录结构

```text
.
├── .env.example
├── .github/
├── .gitignore
├── CONTRIBUTING.md
├── Dockerfile
├── LICENSE
├── Makefile
├── README.md
├── SECURITY.md
├── docs/
├── pyproject.toml
├── requirements.txt
├── standx_bot.py
└── tests/
```

## 测试状态

当前项目提供的是最小运行保护测试，重点覆盖：

- 响应结构校验
- `401` 自动重认证
- 冷启动保护
- 仓位查询节流
- 多单清理
- 熔断
- `DRY_RUN`
- 偏移保护
- 挂单次数保护

## 后续可扩展方向

- 把策略参数做成更完整的 CLI
- 增加纸面交易回放
- 增加 Prometheus 指标
- 增加 Telegram / 钉钉告警
- 增加更细的订单生命周期测试
