# PA Agent — AI K线分析辅助工具（桌面端）


---

面向主观交易者的 **价格行为（Price Action）** AI 辅助决策工具。从 **MT5 / TradingView / Baostock / WeStock / Binance / yfinance / AkShare** 读取 K 线，将结构化 K 线数据与预计算特征送入大模型做**两阶段分析**（市场诊断 → 交易决策），**不是**截图识图，**不连接券商、不执行下单**。

---

## 主要功能

- 📈 **多数据源**：MT5（Windows）、TradingView（全平台）、Baostock（A 股，免费免 Key）、WeStock（A 股/港股/美股，需 Node.js ≥ 18）、Binance（加密货币现货，公开 REST）、yfinance（期货/加密货币）、AkShare（A 股）
- 🧩 **统一数据源注册表**：新增数据源只需在 `pa_agent/data/sources_registry.py` 登记一行；A 股类数据源（含 Baostock / WeStock）共用一个「国内数据源」列表，GUI 下拉、刷新节流、品种占位提示、默认周期都由注册表驱动
- 🧠 **两阶段 AI 分析**：市场诊断 → 策略路由 → 交易决策（限价/突破/市价或不下单）
- 🔄 **增量分析与持续跟踪**：新增 K 线时复用上次结论；开启 `keep_analysis` 后新 K 线收盘自动触发新一轮分析
- 🌳 **决策树可视化**：赛博科幻风格可交互流程图，自动播放闸门→策略路径动画
- 🔮 **未来走势预期**：AI 预测下一根 K 线方向和下一个市场周期位置
- 💬 **分析后自由追问**：完整对话会话管理器，实时推理流 + Token 进度条，对话历史持久化
- 📚 **经验库**：按周期位置检索历史案例供分析参考
- 📝 **完整落盘**：Prompt、原始响应、诊断/决策 JSON、Token 用量、追问记录
- 🛡️ **可配置校验体系**：JSON 校验、一致性检查、语义校验、截断修复、失败自动重试

---

## 环境要求

| 项目     | 要求                                                                    |
| -------- | ----------------------------------------------------------------------- |
| 操作系统 | Windows 10 / 11（主支持）、macOS 12+（TradingView 数据源）              |
| Python   | 3.11+                                                                    |
| 数据源   | MT5 / TradingView / Baostock / WeStock / Binance / yfinance / AkShare **至少配置一种**（WeStock 需额外安装 Node.js ≥ 18；Binance 在国内需代理） |
| 网络     | 可访问所配置的 AI API（如 DeepSeek、PackyAPI 等）                        |

---

## 快速开始

直接在系统中安装（推荐部署在本机）：

```cmd
pip install -e .
python -m pa_agent.main
```

首次启动后在**设置**中填写 **Base URL**、**模型名** 与 **API Key**。

> 如需隔离环境也可创建虚拟环境：`python -m venv .venv` 后激活再 `pip install -e .`。

**安装内容**：PyQt6（GUI 框架）+ pyqtgraph（K 线图表绘图）+ numpy/pandas（数据处理）+ openai（AI API 客户端）+ **akshare/baostock（A 股数据源）** + json 校验、模型定义等全套依赖。

> 若需运行测试（pytest）或代码格式化（ruff/black），额外安装：`pip install -e ".[dev]"`。

**不想装 Python？** 直接下载 Release 里的 `PA_Agent-v*-win64.zip`，解压（建议放在非中文、非 Program Files 路径），
双击 `PA_Agent.exe` 即可。首次启动会在 exe 同级生成 `config/settings.json`，在里面填 API Key。
自行打包见 [打包与发布](docs/打包与发布.md)。

---

## 详细说明

完整操作界面说明见 [`PA_Agent使用文档.md`](PA_Agent使用文档.md)，配置字段说明见 [`config/README.md`](config/README.md)。

---

## 更新日志

### 2026-11-02

**修复（全面审查后的 P0/P1）**

- 🔴 §1.3「极端混乱闸门」方向写反：混乱时反而放行到下单路径
- 🔴 §14 禁止行为闸门用子串匹配，「未触发§14.1，但触发了追高禁止」会被判成清白
- 🔴 「不下单」决策仍保留模型给的三价、`order_type` 仍是突破单，决策会走到下单路径
- 🔴 A 股午休被当成已收盘、tushare 分钟线 1 小时不刷新、周线到下周一才收盘
- 🔴 jsonschema 未安装时校验静默放行（fail-open）
- 🔴 脱敏只覆盖 `provider.api_key`：飞书/Tushare/PushPlus token 与追问落盘曾明文
- 🟠 阶段二重试开关无效、LLM 客户端连接泄漏、全局请求锁串行化、TradingView 代理认证丢失
- 🟠 演示模式触发真实告警、追问线程跨线程操作控件、worker 取消被当成崩溃弹窗

**工程**

- CI 从「只 `import pa_agent`」改为真实跑测试；pytest 加 `--timeout` 与 `--strict-markers`
- 删除 6 个零引用死模块（含 1336 行的 `eastmoney_extended.py`）与 37 个一次性调试脚本
- `config/settings.example.json` 与 `config/README.md` 对齐代码默认值，并加测试防止再次漂移
- ruff 安全自动修复 544 处 + black 全仓格式化；`tools/README.md` 说明保留脚本用途
- 测试：743 passed / 6 failed / e2e 全挂死 → **864 passed / 0 failed**，e2e 4 passed

### 2026-09-05

**修复**

- 🐞 修复「提交分析」点击后无反应的问题：WeStock 数据源输入裸 6 位 A 股代码（如 `002475`）时，程序内部会将其规范化为 `sz002475`，导致每次点击都被误判为「切换品种」，分析永远无法启动。现在提交前按数据源的规范化规则比较品种/周期
- 数据源未连接时，「提交分析」会给出明确的锁定原因（状态栏 + 按钮悬浮提示），不再静默无反应；启动时即检测数据源连接状态并以红色警示提示
- 修复日志文件丢失全部 INFO/DEBUG 记录的问题（此前第三方库的 `"root"` 日志器静默配置误伤了根 logger，导致无法通过日志排查问题）
- 勾选「等待最新K线收盘」且图表尚无数据时，改为自动后台获取 K 线后再等待收盘，不再直接放弃提交
- 切换品种/周期后不再错误提示「下次分析将自动增量」（该提示与实际行为不符）

**其他**

- 新增回归测试覆盖提交分析链路与日志配置（15 例）
- `.gitignore` 排除 `artifacts/`（pytest 临时产物），避免测试垃圾文件入库

---

**免责声明**：本工具仅供学习与研究，不构成投资建议。交易有风险，决策后果自负。

本项目采用 [GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE) 发布。

---