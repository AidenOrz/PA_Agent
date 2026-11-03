# 本地配置说明

本目录下的**运行时文件**默认已被 `.gitignore` 忽略，不会进入 Git 仓库。

仓库同样**不会上传**：`records/`（分析落盘）、`experience/`（经验库内容）、`logs/`、`trade_records/`（交易 CSV/截图）、`.env`、根目录临时图片与个人笔记等。仅源代码、`prompt_engineering/` 策略文本、`tests/` 与 `docs/` 说明文档会进入 GitHub。

## 首次使用

1. 复制模板为本地配置：

   ```cmd
   copy config\settings.example.json config\settings.json
   ```

2. 启动程序，在 **设置** 中填写你的 **API Key**（会加密写入 `api_key_encrypted`）。

   也可直接编辑 `config/settings.json` 中的 `base_url`、`model` 等字段，Key 仍建议通过 GUI 保存以便自动加密。

3. `config/exception_state.json` 由程序在需要时自动创建，一般无需手动复制。结构可参考 `exception_state.example.json`。

4. 如需自定义 TradingView 品种别名，复制模板：

   ```cmd
   copy config\tv_symbol_aliases.example.json config\tv_symbol_aliases.json
   ```

## `settings.json` 字段说明

配置分为七个顶层组：`provider`、`general`、`prompt`、`validation`、`feishu`、`pushplus`、`tushare`。每组的下表列出该组的字段、类型、默认值与说明；模板文件 `config/settings.example.json` 中的默认值与代码完全一致（由测试 `tests/unit/test_settings_example_in_sync.py` 守护）。

### provider — AI 提供商

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `provider.model` | string | `"deepseek-v4-flash"` | 模型名称（须与网关支持的名称一致） |
| `provider.base_url` | string | `"https://api.deepseek.com"` | OpenAI 兼容 API 根地址。DeepSeek：`https://api.deepseek.com`；MiMo：`https://api.xiaomimimo.com/v1`（程序自动处理 `enable_thinking` 与 `reasoning_content` 回放） |
| `provider.api_key` | string | `""` | API Key（明文，内存中临时使用；不持久化到文件） |
| `provider.api_key_encrypted` | string | `""` | 加密后的 Key；留空表示未配置（通过 GUI 保存时自动加密写入） |
| `provider.thinking` | bool | `true` | 是否启用思考/推理类扩展参数（依模型与网关而定）。关闭可 3–5 倍提速但分析质量下降 |
| `provider.reasoning_effort` | string | `"high"` | 推理深度：`low` / `medium` / `high` / `max` |
| `provider.context_window` | int | `2000000` | 用于上下文占用提示的窗口大小（tokens） |

### general — 通用设置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `general.last_data_source` | string | `"mt5"` | K 线数据来源。GUI 下拉：`mt5` / `tradingview` / `baostock` / `westock` / `binance`；仅配置可用：`akshare` / `eastmoney` / `tushare` / `yfinance` |
| `general.last_tradingview_exchange` | string | `""` | TradingView 交易所。空字符串 =（自动）依次探测预设列表。如 `OANDA`、`SSE`、`HKEX` 等 |
| `general.tradingview_proxy` | string | `""` | TradingView WebSocket 代理地址（如 `http://127.0.0.1:7890`）。空字符串 = 自动探测（环境变量 → 系统代理 → 常见本地端口） |
| `general.binance_proxy` | string | `""` | Binance REST 代理地址。空字符串 = 沿用 `tradingview_proxy`，两者都空才自动探测 |
| `general.kline_adjust` | string | `"qfq"` | 东财/宝硕等 A 股数据源的复权方式：`qfq`（前复权）/ `hfq`（后复权）/ `none` |
| `general.last_symbol` | string | `"XAUUSDm"` | 默认品种。MT5 需含后缀（如 `m`），TradingView 用标准名（如 `XAUUSD`） |
| `general.last_timeframe` | string | `"15m"` | 默认周期，如 `1m`、`5m`、`15m`、`1h`、`4h`、`1d` |
| `general.analysis_bar_count` | int | `100` | 提交分析时使用的 K 线数量（2–5000） |
| `general.refresh_interval_ms` | int | `1000` | 图表自动刷新间隔（毫秒） |
| `general.context_warning_threshold_pct` | float | `80.0` | 上下文占用警告阈值（百分比） |
| `general.decision_stance` | string | `"balanced"` | 阶段二交易倾向：`conservative` / `balanced` / `aggressive` / `extreme_aggressive` |
| `general.decision_confidence_threshold` | int | `40` | 下单机会的置信度门槛（0–100）：仅当 `trade_confidence` ≥ 此值时才视为有下单机会（弹窗、告警） |
| `general.enable_next_bar_prediction` | bool | `false` | 是否请求模型给出「下一根 K 线预期」；关闭时省 token |
| `general.structure_flip_cooldown_bars` | int | `3` | 同一结构位 entry 相差 ≤3 跳时，禁止反向新方案的冷却 K 线根数（已收盘，1–50） |
| `general.incremental_max_new_bars` | int | `10` | 增量分析触发阈值：新增已收盘 K 线 ≤ 此值时自动走增量模式（0–500） |
| `general.auto_resume_chart_after_analysis` | bool | `false` | 分析结束后是否自动恢复「图表实时更新」 |
| `general.keep_analysis` | bool | `false` | 持续跟踪分析：新 K 线收盘时自动触发新一轮分析 |
| `general.cancel_keep_analysis_on_retry` | bool | `false` | 校验失败触发重试后自动关闭 `keep_analysis` |
| `general.alert_on_order_opportunity` | bool | `true` | 阶段二给出交易方案时播放警报音、弹窗提示，并自动切换到「决策」页 |
| `general.decision_flow_auto_play` | bool | `true` | 决策树可视化自动播放 |
| `general.decision_flow_play_seconds` | int | `50` | 决策树可视化自动播放时长（秒） |
| `general.decision_flow_default_zoom_pct` | int | `600` | 决策树可视化默认缩放百分比（≥10） |
| `general.stream_pane_font_pt` | int | `11` | 「实时」页等宽字体字号（pt，8–28） |
| `general.chart_seq_label_font_pt` | int | `11` | K 线图上序号标签的字号（pt，6–24） |

### prompt — Prompt 组装调优

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `prompt.stage2_load_full_strategy_library` | bool | `false` | 阶段二是否加载全部 22 个策略文件（通常仅路由匹配的策略文件） |
| `prompt.experience_max_entries` | int | `3` | 经验库最大加载条目数（0–10） |
| `prompt.experience_max_chars_per_entry` | int | `400` | 每条经验最大字符数（100–4000） |
| `prompt.stage1_inject_pattern_briefs` | bool | `true` | 阶段一是否注入模式判定表和速查 brief（减少 missed tags） |

### validation — 校验与重试

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `validation.normalization_mode` | string | `"lenient"` | 归一化模式：`strict`（严格拒绝异常值）/ `lenient`（容忍轻微偏差） |
| `validation.stage1_coherence_checks` | bool | `false` | 阶段一跨字段一致性检查（闸门 trace、逐 K 摘要、模式标签等） |
| `validation.stage2_coherence_checks` | bool | `false` | 阶段二诊断与 trace 交叉检查 |
| `validation.trace_semantic_checks` | bool | `false` | 语义一致性检查（方向/信号逻辑冲突检测） |
| `validation.strict_bar_by_bar_features` | bool | `false` | 严格逐 K 特征校验（开启后对特征字段做严格验证） |
| `validation.disable_truncation_repair` | bool | `false` | 禁用流式 JSON 截断尾部修复 |
| `validation.retry_enabled` | bool | `true` | 校验失败时是否自动重试 |
| `validation.retry_max` | int | `3` | 格式错误（category a）最大重试次数（0–5） |
| `validation.retry_max_semantic` | int | `1` | 语义错误（category c）最大重试次数（0–3） |
| `validation.retry_stage2` | bool | `true` | 阶段二校验失败时是否重试 |

### feishu — 飞书机器人推送

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `feishu.enabled` | bool | `true` | 是否启用飞书推送 |
| `feishu.webhook_url` | string | `""` | 自定义机器人 Webhook 地址；留空 = 不推送 |
| `feishu.secret` | string | `""` | 自定义机器人签名密钥（开启「加签」时填写） |
| `feishu.app_id` | string | `""` | 应用机器人 App ID（走应用消息时填写） |
| `feishu.app_secret` | string | `""` | 应用机器人 App Secret |
| `feishu.notify_on_order_only` | bool | `true` | 仅在阶段二给出下单机会时推送；`false` 则每轮分析都推送 |

以上字段中的 `webhook_url`、`secret`、`app_secret` 已被日志脱敏层登记，写日志/崩溃报告时会被替换为 `***`。

### pushplus — PushPlus 微信推送

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `pushplus.enabled` | bool | `false` | 是否启用 PushPlus 推送（仅配置文件，无 GUI 入口） |
| `pushplus.token` | string | `""` | PushPlus 用户 token；已登记脱敏 |

### tushare — Tushare Pro 数据源

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `tushare.token` | string | `""` | Tushare Pro token。**注意：与 `provider.api_key` 不同，此字段以明文保存在 `config/settings.json`**（该文件已被 `.gitignore` 忽略），请勿提交或分享该文件；已登记脱敏 |

## 安全提醒

- **不要**将 `config/settings.json`、`config/exception_state.json`、`config/tv_symbol_aliases.json` 提交到 Git。
- 若曾误提交 API Key，请立即在服务商处**作废并轮换**密钥。
- 建议在仓库根目录执行：`powershell -ExecutionPolicy Bypass -File tools\setup_git_secrets.ps1`
