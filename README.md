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

### 2026-11-07（第二轮：DeepSeek 缓存命中率优化）

依据 [`docs/会话管理与DeepSeek缓存优化开发文档.md`](docs/会话管理与DeepSeek缓存优化开发文档.md)
第 1 步（观测 + 续链缺陷修正）落地：

- 🟠 **增量续链改追加式**：`build_incremental_stage1` 此前每次只抽旧第一条 user 重建四条消息——上一轮增量任务（携带上一轮新增棒）被整条丢弃，历史回答被反复重写。现在优先整体复用上一轮已完成请求链（chain 形态下 = S1 全链 + S2 任务与回答，前缀逐字节相同），仅在尾部追加增量任务；提示词升级（system 不一致）时新建上下文段、回退重建
- 🟠 **S2 链去重**：成功链末尾已含原始 assistant，不再追加归一化副本（每次 S2 省约 1.2K token）；缺回答时追加原始 reply content（含 ```json 围栏原样保留），不再重新美化 JSON——归一化结果与请求历史分离
- 🟠 **K 编号诚实化**：增量任务不再宣称旧表「K线序号已重新编号，K1=当前最新」（从未发生，模型据此引用错棒）；仅当逐棒核对（与 `compute_incremental_bar_delta` 同源锚定规则）确认无历史修订时，才给出精确映射「旧表 K{j} = 本轮 K{j+m}」，对齐失败（历史修订/复权变化）明示以本消息数据与编号为准
- 🟠 **追问实际历史**：`FollowupTurn` 新增 `actual_user` 字段，展示问题与实际请求内容（含行情快照表）分开保存；第二轮续接历史重发实际内容，不再用简短问题替换导致前缀从旧 user 位置断开
- **逐请求观测**：S2 响应落盘实际 `cache_mode`（provider 不支持链式时自动降级 standalone——配置默认 ≠ 实际形态）；追问 usage 记录实际服务模型名（网关别名可能改写）与单次命中率
- 🐞 **小修复**：`context_window` 默认 2,000,000 → 1,000,000（DeepSeek 官方当前上下文 1M，旧默认让上下文提示基于达不到的窗口）；状态栏不再硬编码「缓存按 10% 价格计费」（官方直连缓存价为未命中价的 2%，第三方网关以实际报价为准）；Token 展示拆分「历史累计消费」与「当前请求上下文占用」两个口径，进度条不再被多轮累计虚增

### 2026-11-07

**全面审查修复轮（P0/P1 全部关闭，分支 `dev/review-fixes`）**

审阅报告见 [`docs/代码审阅报告_2026-11-07.md`](docs/代码审阅报告_2026-11-07.md)。

- 🔴 **P0** 东财 Baostock 兜底成交量未换算（股/手差 100 倍）：东财日线 qfq 默认走该兜底、分钟线超窗口也切兜底，同一张图成交量单位随路径翻转，放量判断全部失真。换算收敛到 `ashare_common.baostock_shares_to_lots`（带 NaN 防御）
- 🟠 **P1 数据层** A股 4h 重采样改按交易日锚定（此前按位置每 4 根切桶，盘中所有历史桶跨日拼接、收盘价属于下一天）；Tushare 上证系指数后缀（000016/000905/000852 误挂 .SZ 恒空）与 399 深证系指数识别（被当个股请求恒空）；周/月线 forming 口径统一到周期末 15:00（此前 15:00 后半截周线被当已收盘 K1，且东财/AkShare 与 Baostock 口径相反）
- 🟠 **P1 AI 管线** 重试篡改检测对 markdown 围栏输出 fail-open（fenced JSON 解析失败 → 检测静默失效）；§1.3/§1.2 混乱闸门补程序侧不变量 `validate_chaos_gate_invariant`（coherence 检查关闭时仍生效），「极端混乱却 proceed」现在会被拒绝
- 🟠 **P1 GUI** closeEvent 补停追问线程（此前漏掉：运行中 QThread 被析构会 qFatal abort，且线程还在写追问落盘）；追问快照/TV 探测回调三处跨线程读 QComboBox 收口（改为读 GUI 线程同步的 str 缓存）
- 🟠 **P1 安全** 追问落盘脱敏接入共享凭据注册表（`util.mask_secret`）：飞书 webhook、PushPlus/Tushare token 粘进追问框不再明文写入 `records/pending/*.followups.jsonl`
- 🟠 **P1 缓存** `stage2_cache_mode` 默认 standalone → chain（生产日志实测 standalone S2 命中仅 33-48%，chain 复用刚处理过的 S1 前缀且免重发 K 线表；旧文档 93.9% 为全策略库配置所测）；修复增量续链的原位刷新破坏逐字节前缀（`build_incremental_stage1`）
- 🟠 **P1 构建** Release 产物附 SHA256 校验和（`-SkipTests` 与 `-Publish` 互斥）；e2e smoke 收进 nightly CI（`workflow_dispatch` 可手动触发）
- 样式：black 全仓收敛（此前 3 个测试文件漂移），ruff 维持基线 197 条

### 2026-11-04

**首个 Windows 桌面版发布（v0.1.0）**

- Release 提供免安装的 `PA_Agent-v0.1.0-win64.zip`（onedir，解压即用），打包流程见 [打包与发布](docs/打包与发布.md)
- 提示词可直接改：把 `prompt_engineering/` 放到 exe 同级即覆盖内置版本，无需重打包

**阶段二 KV 前缀缓存优化（命中率 19% → 预期 76%）**

- 🔴 提示词按缓存前缀重排：静态策略库与输出契约前置，动态块后置，跨轮次公共前缀 30% → 76%
- 新增 `prompt.stage2_cache_mode`（`standalone` 默认 / `chain`）
- 🟠 界面缓存率分母改用单次请求，不再把阶段一 + 阶段二 prompt 相加

**数据源**

- 新增 Baostock（A 股，免费免 Key）与 Binance（加密货币现货，公开 REST）
- 数据源清单收敛到 `pa_agent/data/sources_registry.py`

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