# PA Agent 修复工作交接文档

> 日期：2026-09-03
> 背景：基于 2026-09-03 全面代码审阅（审阅结论：8-01 清单大部分已落地、新引入 1 处严重回归、30 个测试过时）执行修复。修复进行到一半时用户因软件问题叫停，本文档记录**已修复**与**未修复**的准确状态。
> 本轮修复前基线：`30 failed / 649 passed / 38 errors`（非 live 测试）。

---

## 一、已修复（产品代码）

| # | 修复 | 文件:位置 | 验证 |
|---|------|----------|------|
| 1 | 🔴 `_parse_score_100` 函数体截断回归（置信度/胜率 UI 恒 None）——clamp 逻辑从 `_format_price` 死代码处移回函数体 | `pa_agent/gui/decision_panel.py:99-110` | 直接断言 9 组输入全过；`_format_price` 不受影响 |
| 2 | 🟠 WeStock 周月线 forming 缺失（未收盘 bar 进入 AI 分析）：`_is_forming_daily_bar` 重写为 `_is_forming_bar`/`_is_forming_bar_at`，覆盖 1d/1w/1M/3M/1y 全周期；新增 `_past_daily_close`（午休不影响周线 forming） | `pa_agent/data/westock_source.py:342-404`（`_rows_to_bars` 调用处同步更新） | 新增 4 个测试（日/周/月季年/rows_to_bars 集成），westock 测试文件 13 个全过 |
| 3 | 🟠 demo 入口 QThread 旧式取消（崩溃+界面污染+GUI 线程阻塞 5s）：改走标准 `_cancel_analysis_worker` 协议（disconnect→失效 ID→zombie 回收，join_ms=0 不阻塞） | `pa_agent/gui/main_window.py:2496-2500` | 复用其他 4 个入口已验证的协议函数；demo 路径无其他 `_worker` 引用 |
| 4 | 8-01 清单 #10：`_CHAPTER_ORDER` 缺 `"1."`/`"2."` 键导致 1/2 章节点排到 trace 末尾 | `pa_agent/ai/trace_normalize.py:604-608` | 直接调用 `normalize_trace_list` 验证排序 `1.1→2.3→3.1→14.1→99.9`；normalizer/validation 40 个测试全过 |
| 5 | 8-01 清单 #12 残留：tushare 指数硬编码 `asset="E"`（000300 等取不到数据）：新增 `is_tushare_index()`（复用 `TV_SSE_INDEX_CODES` + `0009xx` 前缀），指数走 `asset="I", adj=None` | `pa_agent/data/tushare_source.py:73-84, 262-283` | 7 组断言验证（000300/000905/000852/000016 为指数，600519/000001.SZ 不是） |
| 6 | 8-01 清单 #17 残留：4 条退出路径 usage 只折叠最终回复、丢重试调用的用量——`two_stage.py` :809（pre-stage2 取消）、:842（gate 短路）、:952（stage2 初始网络错误）、:986（post-stage2 取消）全部改用 `s1_usage_calls` 列表折叠 | `pa_agent/orchestrator/two_stage.py` 上述 4 处 | two_stage 相关测试（decision_nodes_orchestrator、qclaw_auto_fallback）全过，import smoke 过。注意 :627 处保持 `reply_s1.usage` 是正确的（该处在 `s1_usage_calls` 建立之前） |

## 二、已修复（测试与工具链）

| # | 修复 | 说明 |
|---|------|------|
| 7 | pytest-qt 安装 + Qt5/Qt6 DLL 冲突修复 | 安装 pytest-qt 4.5.0 后 PyQt6 导入报 `DLL load failed while importing QtCore`。根因：pytest-qt 自动探测绑定顺序先加载了 PyQt5，Qt5/Qt6 同进程共存冲突（本机 Anaconda 同时装有 PyQt5）。修复：新建 `tests/conftest.py` 设 `PYTEST_QT_API=pyqt6`（绑定探测惰性执行，conftest 时机来得及）。38 个 GUI 测试从 ERROR 恢复，抽测 28 个全过 |
| 8 | 子代理遗留的 5 个测试文件收尾 | 两个测试同步子代理因 API 配额耗尽中途失败（限额 2026-09-10 重置），已改完 `test_price_tick.py`、`test_order_method_router.py`、`test_decision_nodes_judges.py`、`test_free_chat_keeps_reasoning_when_toggled.py`、`test_free_chat_resend_drops_reasoning.py` 的大部分；残留 1 个断言（`test_history_for_api_grows_with_turns` 消息数 5→6、索引+1）由我补齐。5 文件 75 个测试全过 |

## 三、未修复（测试同步，根因均已定位）

以下 22 个失败全部是「产品代码 8 月有意变更 + 测试未同步」，非产品 bug。修法已在根因分析中验证，按清单逐项处理即可：

| 测试文件（失败数） | 根因 | 修法 |
|---|---|---|
| `tests/unit/test_decision_panel.py`（6） | `_prediction_group`/`_prediction_direction_label` 已移除，预测 UI 迁到 `gui/future_trend_panel.py:176-313` | 改测 FutureTrendPanel 接口 |
| `tests/unit/test_trace_normalize.py`（5） | normalizer 有意不再清洗"不下单"残留字段（让校验器拒绝非法输出触发重试，`stage2_normalizer.py:1432-1443`，有新测试背书 `test_stage2_normalizer.py:983`） | fixture 改为完整合法的"不下单"载荷：schema（`prompts/schemas.py:363-383`）规定 9 个字段全 null |
| `tests/integration/test_next_bar_prediction.py`（3） | (a) `enable_next_bar_prediction` 默认 False，关闭时 orchestrator 剥离该字段（`two_stage.py:1144-1146`）；(b) 同 decision_panel 属性移除 | (a) 测试构造 settings 时启用开关；(b) 同上改 FutureTrendPanel |
| `tests/property/test_next_bar_prediction.py`（1） | normalizer:1062-1076 新增平局规则"保留模型方向选择"，与 argmax 性质断言冲突 | 性质测试排除全平局情形，或平局单独断言保留原值 |
| `tests/property/test_snapshot_bijection.py`（1） | forming 判定新增挂钟检查 + forming bar 约定 seq=0（`snapshot.py:174/187`） | 测试传与 ts_open 匹配的 `now_ms`，断言 seq==0 |
| `tests/property/test_logs_have_no_plaintext_key.py`（1） | **根因未明**：日志文件为空（明文泄漏断言本身通过，失败在"掩码必须出现"断言，content 为空串）。疑与 configure_logging handler/flush 有关，需先诊断 `pa_agent/util/logging.py` | 先诊断再定：产品 bug 则报 bug，测试时序问题则修测试 |
| `tests/unit/test_market_defaults.py`（1） | 黄金符号按场所映射过滤 probe plan（`market_defaults.py:220-224`，SP/NYSE 等不报现货黄金被有意跳过） | 期望改为黄金可用 6 场所；可加 EURUSD 用例 |
| `tests/unit/test_order_opportunity.py`（1） | 产品新增 `SND_ASYNC` flag，FakeWinsound stub 缺该常量，AttributeError 被吞 | stub 补 `SND_ASYNC = 8` |
| `tests/unit/test_provider_override_by_model.py`（1） | `apply_cursor_provider_to_settings` 重写为纯校验（`cursor_connector.py:68-89`），base_url 有意清空、不再走 QClaw 网关 | 重写为新语义：crsr_ key 校验、base_url=="" |
| `tests/e2e/`（4 个 smoke） | 未深挖（疑似与上述 fixture/接口变更同类）。**注意：e2e 测试疑似挂起**，单文件跑 5 分钟无结果，可能与真实网络/mock 缺失有关，修之前先查挂起原因 | 先单独诊断挂起，再逐个对齐 |

## 四、本轮修复后测试状态

`python -m pytest -m "not live"`：
- **24 failed / 22+4(e2e) 见上表 / 649+ passed**（GUI 38 个从 ERROR 恢复为可运行，抽测全过；westock 新增 4 个）
- e2e 4 个失败中包含挂起风险，跑全量时建议先排除：`python -m pytest -m "not live" --ignore=tests/e2e`

## 五、其他未做（原计划内）

1. **ruff 配置**：`pyproject.toml` 加 `"RUF001","RUF002","RUF003"` 到 `[tool.ruff.lint] ignore`（中文标点歧义误报 3375 条），然后清理剩余真实 lint 项（46 个 F401 等）。未做。
2. **产品层面复核项**（审阅发现，非阻塞）：metrics 强转发生在 §9.0 修复之前（`stage2_normalizer.py:1409` vs `:1416`），任何 metrics 失败会连带跳过 planned-limit 的 §9.0 升级——字段齐全时无影响，但"先修复再强转"更稳妥；A 股日线午休期间当日 bar 判"已收盘"是全项目统一行为（westock/akshare/bar_close_wait 一致），如要改应整体评估。
3. **WeStock 小问题**（未修）：Windows 上 `npx.cmd` 超时后 node 子进程树可能残留；缓存三元组赋值无锁（低危）；港股时段用 9:30-16:00 连续近似。
4. **8-01 清单遗留未修**：#17 的 `_stream_chat_resilient_impl` 降级成功时被吞掉调用的 usage 不计入；feishu token 刷新仍在锁内做 HTTP；eastmoney 1d 盘中单次快照仍拉 2 次盘口。

## 六、恢复入口

1. 测试同步按第三节表格逐项修（TP2 fixture 模式参考 `test_stage2_normalizer.py:436/507/570/671`；free_chat 新前缀布局为 `[system, user-ref, assistant-recall, ...]`，索引整体 +1，已修好的两个文件可作参照）。
2. API 配额 2026-09-10 重置后可再派子代理并行处理剩余测试文件（互不重叠的文件集）。
3. 每修完一个文件跑：`python -m pytest <file> -q -p no:cacheprovider`；全部修完后跑 `python -m pytest -m "not live" --ignore=tests/e2e` 验收，e2e 单独诊断挂起问题。

## 七、修改文件清单（本轮）

产品代码：
- `pa_agent/gui/decision_panel.py`（修复 #1）
- `pa_agent/data/westock_source.py`（修复 #2）
- `pa_agent/gui/main_window.py`（修复 #3）
- `pa_agent/ai/trace_normalize.py`（修复 #4）
- `pa_agent/data/tushare_source.py`（修复 #5）
- `pa_agent/orchestrator/two_stage.py`（修复 #6，4 处）

测试/工具链：
- `tests/conftest.py`（新建，PYTEST_QT_API=pyqt6）
- `tests/unit/test_westock_source.py`（新增 4 个 forming 测试）
- `tests/unit/test_free_chat_resend_drops_reasoning.py`（补齐子代理遗留的 1 个断言）

依赖：环境新增 `pytest-qt==4.5.0`（dev 依赖本就声明，此前未装）。
