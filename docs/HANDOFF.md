# PA Agent 交接文档

> 更新：2026-11-03 ｜ 已全部合入 `main` 并推送（`c82254e`），CI 首次跑通
> 上一版停留在 2026-09-03 的修复中途（当时 `30 failed / 649 passed / 38 errors`），
> 本版按「接受一次全面审查 → 依次修 P0/P1/P2/P3」的推进结果重写。

## 一、当前状态（实测）

| 项目 | 结果 | 命令 |
|------|------|------|
| 非 live 测试 | **934 passed / 38 skipped / 0 failed** | `python -m pytest -m "not live" --ignore=tests/e2e` |
| e2e smoke | **4 passed**（无挂起） | `python -m pytest tests/e2e` |
| ruff | 196 条剩余（多为 E402 延迟导入、SIM102 可合并 if），无自动修复项 | `python -m ruff check pa_agent tests tools` |
| black | 全部通过（282 个文件） | `python -m black --check pa_agent tests tools` |
| CI | 首次通过（windows-latest / Python 3.11 / `QT_QPA_PLATFORM=minimal`） | `gh run view 41478417351` |
| 规模 | 137 个源文件 / 140 个测试文件（其中 127 个 `test_*.py`）/ 145 次提交 | — |

审查开始时的基线是 743 passed / 39 skipped / **6 failed**，e2e 4 个全部挂死（需强杀进程）。

### 新增数据源（分支 `dev/data-sources-baostock-binance`）

1. **统一数据源注册表** `pa_agent/data/sources_registry.py`：清单原本散在 factory（3 处）、settings（第二份
   Literal）、market_defaults（1 处元组）、main_window（2 处元组、1 处周期回落分支）共 7 处，现在全部查注册表。
2. **国内数据源共用列表** `DOMESTIC_A_SHARE_KINDS = ("baostock","westock","akshare","eastmoney","tushare")`，
   由 `SourceSpec.domestic` 派生。WeStock 算国内源（原生接受 6 位代码）；TradingView 只算「能覆盖」不算国内源，
   否则黄金/加密品种会被改写成 6 位代码。
3. **Baostock 数据源** `baostock_source.py`：复用已有 `_BaostockSession`（同一个锁/登录/socket），周期
   1d/1w/1M/5m/15m/30m/1h（4h 由 1h 重采样），周线按 ISO 周、月线按自然月判未完成（Baostock 的周/月线
   时间戳是「周内最后一个交易日」/「月末交易日」，按日期相等判断会永远当成已收盘）。
4. **Binance 数据源** `binance_source.py`：公开 REST `GET /api/v3/klines`，无需 Key；symbol 归一
   （`btc/usdt`、`BTCUSDT.P` 等），只有最后一根可能是未完成 K 线；代理优先级 `binance_proxy` →
   `tradingview_proxy` → 自动探测。
5. **`proxy_env.py`**：把 TradingView 里的代理探测（手动/环境变量/系统注册表/常见端口）抽成共用模块，
   TradingView 的静态方法改为一行转发（对外签名不变，原有测试不需要改）。
6. **口径修正（`5cfe917`）**：Baostock 成交量是「股」而其余 A 股源用「手」（实测差 100 倍），统一换算；
   Baostock `adjustflag` 是 1=后复权 / 2=前复权 / 3=不复权，而 `akshare_source` 原映射把 hfq 与 none
   写反（选「不复权」拿到后复权价），现由 `eastmoney_baostock.baostock_adjust_flag()` 统一。

## 二、这一轮修了什么

按严重程度分四批，每批一个独立分支、若干可回滚的提交。详细原因写在每个提交的正文里，
这里只列结论与位置。

### P0（10 项，分支 `fix/p0-audit-fixes`）

1. **§1.3 闸门方向写反**：`trace_normalize._repair_gate_result` 把「是否极端混乱」判成 `answer=="否"`，
   而 §1.3 的语义是回答「是」才阻断 —— 混乱时反而放行到下单路径。现改为 `== "是"`。
2. **数据层收盘判定三处不一致**：A 股午休被当成已收盘（`bar_close_wait` 用 09:30-11:30/13:00-15:00
   判 forming，而 `eastmoney_source` 用含午休的 `ashare_head_bar_live`）；tushare 分钟线缓存 TTL 恒定
   1 小时且头一根永远 `closed=True`；周线算成「下周一 0 点收盘」。统一到 `ashare_is_forming_bar()`
   与新的 `_bar_close_ms()`。
3. **GUI 演示模式副作用**：演示回放会真的触发告警弹窗与追问线程；追问线程跨线程直接操作控件；
   worker 取消被当成错误弹「程序异常」；`closeEvent` 漏停若干后台线程。
4. **脱敏只覆盖 `provider.api_key`**：飞书 token、Tushare token、PushPlus token、追问落盘内容全部明文。
   改为 `register_settings_secrets()` 统一登记 + `mask_known_secrets_in_text()` 供崩溃日志复用。
5. **jsonschema 缺失时静默放行**：`pip install` 漏装依赖会变成「校验永远通过」。改为 fail-closed。
6. **CI 只 `import pa_agent`**：新增真实跑测试；`pytest-timeout` 防挂死；pre-commit 正则重写。

### P1（4 项，分支 `fix/p1-audit-fixes`）

1. **§14 闸门子串启发式**：「未触发§14.1，但触发了追高禁止」会被判成清白。新的 `section14.py` 按从句
   切分 + 否定前缀识别，无法判定时按违规处理。
2. **不下单决策仍带三价**：`route_order_method` 遇到「不下单」只 `return []`，模型给的价格照旧留着，
   `order_type` 还是「突破单」，决策仍能走到下单路径。改走 `clear_decision_to_no_order()`。
   stage1 缺失也从「归一成 unknown 后全改不下单」改为直接早退（不要伪装成主动拒单）。
3. **规范化层编造证据**：`follow_through` 取不到时硬写 `True`；`signal_bar` 可能被改写成帧里不存在的
   序号；`stale` 被洗成 `pending`。
4. **阶段二重试开关无效 + 客户端泄漏 + 全局请求锁串行 + 代理认证丢失 + 控制台闪烁**。

### P2（工程债，分支 `chore/p2-p3-debt`）

- 删除 6 个整模块零引用的死文件（`eastmoney_extended.py` 1336 行、`settings_dialog.py` 503 行等）与空包
  `pa_agent/security/`；拆掉 `analysis_mode` 这个**从未存在**的字段（`getattr` 永远返回默认值，两种模式
  从未被区分）。
- `config/settings.example.json` 用 `Settings().model_dump()` 重新生成（原文件 8 处值与代码不符、缺 13 个
  字段）；`config/README.md` 补齐 7 个顶层组与全部字段。新增 `tests/unit/test_settings_example_in_sync.py`
  把模板、README、代码三者绑定。
- 删除 37 个一次性调试脚本（19000 网关探针、厂商连通性测试、pending 统计），保留 6 个仍有用的并写
  `tools/README.md`；`tools/dump_pa_stack.bat` 去掉写死的 `E:\PA_Agent` / `E:\anaconda3`，并修正
  `python -m pyspy`（不存在的模块）为真实的 `py-spy` 可执行文件。
- 依赖：`tvdatafeed` 补 commit pin；显式声明 `matplotlib`、`requests`；pytest 加 `--strict-markers`。
- `ruff check --fix`（544 处）+ `black`（247 个文件）一次性对齐，作为独立提交，便于 `git blame --ignore-rev`。

### P3（过程中的小问题）

- `closeEvent` 未调用决策树可视化面板的 `shutdown()`，三个 QTimer 会在场景销毁后继续 tick。
- `tests/e2e` 曾全部挂死：根因是 `show_validation_debug_dialog` 的模态框阻塞 `qtbot.waitUntil`；
  而 4 个用例本身还依赖 `ctx.settings`（默认 `None`）与 `ctx.data_source`（默认 `None`）。

### 通用设置「记不住、每次都重置」（本轮新增）

用户反馈「通用设置记不住设置，每次都重置」。先用四组探针证明保存/加载链路本身没丢值：
对话框 `_on_save` → 磁盘 → `load_settings` → 新建对话框，20 个控件全部 round-trip 一致；
连续 5 次「改一个字段→保存」逐次落盘并保持；磁盘与 `load_settings` 逐字段无差异。
真正的成因有三条：

1. **启动时把 `keep_analysis` 强制改回 False**（`main_window.py` 的 `_setup_ui`）：只改内存不落盘，
   于是重启后通用设置里「持续跟踪分析」永远显示未勾选；之后任何一次整份保存（切品种、切数据源、
   切 TV 交易所、勾选持续跟踪、重试取消）都会把 False 写回磁盘，用户此前的勾选被永久抹掉。
   现改为按持久化值还原勾选框（`blockSignals` 屏蔽信号，启动阶段仍不会自动拉数据），并同步
   「等待K线收盘」的锁定状态。
2. **设置对话框用 `Settings()` 兜底**：`ctx.settings is None` 时（直接 `AppContext()` 构造）三个对话框
   都在一份全新默认对象上编辑，保存即用默认值覆盖磁盘。新增 `_ensure_settings_loaded()`：缺 settings
   时 `load_settings()` 读盘，而不是造一份默认值。
3. **跑测试会改写用户真实的 `config/settings.json`**：e2e 的 `_on_symbol_or_tf_changed` 会调
   `save_settings()` 写到默认路径，而 `save_settings` 还会用 DPAPI 重新加密 `provider.api_key`；
   实测一次 `pytest` 就把文件改成 `analysis_bar_count=20 / last_symbol=EURUSD`，并把 API key 换成
   测试 key。`tests/conftest.py` 新增 autouse fixture，把 `SETTINGS_JSON_PATH` 指到每个用例自己的
   tmp 目录；三个设置对话框里 `SETTINGS_JSON_PATH` 的模块级快照也改为调用时导入（否则 patch 不到）。

**保存后立即生效**：`refresh_interval_ms`（RefreshLoop 构造时快照）、`context_warning_threshold_pct`
（ledger 在 bootstrap 时快照）、`keep_analysis`（只在启动时读）此前都要重启才生效。
`_open_general_settings_dialog` 现在先快照这几个值，保存后由 `_apply_general_runtime_settings()` 按差异
重启 RefreshLoop、调 `SessionTokenLedger.set_warn_pct()`、同步工具栏勾选框；实时页字号由
`_ai_sidebar.bind_settings()` 负责。TV 交易所的初始值也改为读 `ctx.settings`，不再二次 `load_settings()`。

回归测试：`tests/unit/test_gui_settings_persistence.py`（10 例，含「保存设置不得碰真实配置文件」）。

### 首次真正跑起来的 CI（3 个后续提交）

CI 过去两年只执行 `import pa_agent`，等于从未验证过任何东西。改成真实跑测试后，连续暴露三个问题：

1. **`_DecisionNode.paint` 场景销毁后崩溃**（`b2a57cd`）：`_BranchEdge.phase()` 与
   `_TerminalNode._anim_phase()` 直接 `self.scene()`，而 `QGraphicsScene.clear()` 会销毁 C++ 对象；
   排队中的重绘仍会进 `paint()`，此时抛 `RuntimeError: wrapped C/C++ object has been deleted`，
   异常逃进 Qt 事件循环 → 进程 abort（`exit -1073741819`，连 pytest 汇总都不打印）。
   修复：新增 `_scene_anim_phase()` 捕获 `RuntimeError` 后回退本地相位。
2. **无桌面会话时的 QGraphicsView 重绘**：`qwindows` 平台在没有交互式桌面时，Qt 的 backing store
   反复重绘会交给 `paint()` 一个不可用的 `QPainter`，同样 abort。CI 设 `QT_QPA_PLATFORM=minimal`
   （`offscreen` 在本地也能复现，不能用；`minimal` 全绿）。
3. **测试夹具放在被 gitignore 的 `tools/` 下**（`c82254e`）：`tests/unit/test_json_validator.py` 读
   `tools/stage2_raw_sample.txt`，本地有、CI 检出没有 → 本地绿 / CI 红。夹具挪到
   `tests/fixtures/stage2_raw_sample.txt` 并纳入版本控制。

**教训**：本地“全绿”可以骗人。验收 CI 相关的改动必须对着**干净检出**验证，
`git clone --depth 1 file:///E:/PA_Agent .tmp-cleancheck` 再在克隆目录里跑一遍，才能暴露这类
“依赖了未跟踪文件”的问题。

## 二·五、v0.1.0 发布（2026-11-04）

首个 Windows 桌面版已发布：<https://github.com/AidenOrz/PA_Agent/releases/tag/v0.1.0>，
产物 `PA_Agent-v0.1.0-win64.zip`（165 MB，解压 390 MB，onedir）。

- 打包链路：`PA_Agent.spec` + `tools/build_release.ps1`，说明见 `docs/打包与发布.md`
- `pa_agent/config/paths.py` 拆成 `PROJECT_ROOT`（exe 同级，可写）与 `BUNDLE_ROOT`（`sys._MEIPASS`，只读），
  提示词按「exe 同级 → 内置」解析，`PA_AGENT_PROMPT_DIR` 可覆盖；测试 `tests/unit/test_paths_frozen.py`
- spec 的 `excludes` 是刻意清单：多余 Qt 绑定会直接中止构建，scipy 会拖进 dask/torch（980 MB → 390 MB）
- 发布前的同批改动：阶段二提示词按缓存前缀重排、`prompt.stage2_cache_mode`、界面缓存率分母改用单次请求

**已知限制**：未做代码签名（SmartScreen 提示未知发布者）；只有 onedir 无单文件版；
MT5 数据源要求本机装 MT5 终端，否则日志出现 `IPC initialize failed, MetaTrader 5 x64 not found`（其它数据源正常）。

## 三、没做 / 已知遗留

1. **ruff 剩余 198 条**未清理：都是需要逐条判断语义的（E402 延迟导入是刻意的循环依赖规避、SIM102
   合并 if 会改变可读性）。CI 里该步骤仍是 `continue-on-error: true`（advisory）。
2. **`pa_agent/records/pending_writer` 的历史 pending 归一化**会把 `stale` 洗成 `pending`，未动。
3. **`decision_nodes` 的若干 `return []` 早退**只修了会改变下单结论的那几处，其余保留。
4. **`docs/REPAIR_PLAN.md`、`docs/WESTOCK_INTEGRATION_PLAN.md`** 是历史计划书，未随本轮同步。
5. **`analysis_mode`** 现在是一个显式 no-op：`two_stage.py` 里 `analysis_mode = "original"` 并附注释。
   若要真的做两种模式，需要先在 `GeneralSettings` 里加字段，再补分支。

## 四、恢复入口

```cmd
git switch main
E:\anaconda3\python.exe -m pytest -m "not live" --ignore=tests/e2e --timeout=300
E:\anaconda3\python.exe -m pytest tests/e2e
:: 验证“干净检出也能过”（CI 环境等价）：
git clone --depth 1 file:///E:/PA_Agent .tmp-cleancheck && cd .tmp-cleancheck && pytest -m "not live" --ignore=tests/e2e
```

- 改 GUI 相关代码：先跑 `tests/unit/test_tv_probe_nonblocking.py`、`test_gui_state_and_busy.py`、
  `test_decision_flow_animation.py`，这三个覆盖了本轮 GUI 修复的全部回归点。
- 改数据层收盘/缓存逻辑：`tests/unit/test_bar_close_wait.py`、`test_ashare_trading_calendar.py`、
  `test_tushare_source.py`。
- 改设置项/持久化：`tests/unit/test_gui_settings_persistence.py`（启动还原「持续跟踪分析」、
  保存后即时生效、测试不得改写真实 `config/settings.json`）。
- 改数据源清单/新增数据源：`tests/unit/test_sources_registry.py`（注册表不变量）、`test_baostock_source.py`、
  `test_binance_source.py`；说明见 `docs/数据源注册表与新数据源.md`。
- 改校验/规范化：`test_section14_gate.py`、`test_no_order_helper.py`、`test_validation_lenient_fixes.py`。
- 调试挂死：`tools/dump_pa_stack.bat`（窗口卡死时转储线程栈）或 pytest 的 `faulthandler`。
- 提交前：`black pa_agent tests tools` + `ruff check`，勿新增 lint 项。

## 五、约定（详见 `CONTRIBUTING.md`）

- 分支：功能 `dev/…`、修 bug `fix/…`、清理 `chore/…`；提交信息中文 + 前缀（`修复:` / `样式:` / `文档:`）。
- 临时文件一律 `.tmp-` 前缀，任务结束清理（`.gitignore` 已忽略 `/.tmp-*`）。
- 不要在提交里混入 `config/settings.json`、`logs/`、`records/`。