# PA Agent 交接文档

> 更新：2026-11-03 ｜ 已全部合入 `main` 并推送（`c82254e`），CI 首次跑通
> 上一版停留在 2026-09-03 的修复中途（当时 `30 failed / 649 passed / 38 errors`），
> 本版按「接受一次全面审查 → 依次修 P0/P1/P2/P3」的推进结果重写。

## 一、当前状态（实测）

| 项目 | 结果 | 命令 |
|------|------|------|
| 非 live 测试 | **866 passed / 38 skipped / 0 failed** | `python -m pytest -m "not live" --ignore=tests/e2e` |
| e2e smoke | **4 passed**（无挂起） | `python -m pytest tests/e2e` |
| ruff | 198 条剩余（多为 E402 延迟导入、SIM102 可合并 if），无自动修复项 | `python -m ruff check pa_agent tests tools` |
| black | 全部通过 | `python -m black --check pa_agent tests tools` |
| CI | 首次通过（windows-latest / Python 3.11 / `QT_QPA_PLATFORM=minimal`） | `gh run view 41478417351` |
| 规模 | 133 个源文件 / 135 个测试文件（其中 122 个 `test_*.py`）/ 139 次提交 | — |

审查开始时的基线是 743 passed / 39 skipped / **6 failed**，e2e 4 个全部挂死（需强杀进程）。

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
- 改校验/规范化：`test_section14_gate.py`、`test_no_order_helper.py`、`test_validation_lenient_fixes.py`。
- 调试挂死：`tools/dump_pa_stack.bat`（窗口卡死时转储线程栈）或 pytest 的 `faulthandler`。
- 提交前：`black pa_agent tests tools` + `ruff check`，勿新增 lint 项。

## 五、约定（详见 `CONTRIBUTING.md`）

- 分支：功能 `dev/…`、修 bug `fix/…`、清理 `chore/…`；提交信息中文 + 前缀（`修复:` / `样式:` / `文档:`）。
- 临时文件一律 `.tmp-` 前缀，任务结束清理（`.gitignore` 已忽略 `/.tmp-*`）。
- 不要在提交里混入 `config/settings.json`、`logs/`、`records/`。