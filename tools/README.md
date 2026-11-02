# tools/ — 开发者工具

这里的脚本**不参与**运行时的任何代码路径，也不被 `tests/` 引用。它们只在手工排障或一次性数据核对时运行，因此不在 CI 覆盖范围内。

约定：脚本一律使用**相对仓库根目录**的路径（`Path(__file__).resolve().parents[1]`），不写死盘符，换机器即可运行。

| 脚本 | 用途 | 运行方式 |
|------|------|----------|
| `dump_pa_stack.bat` | 界面卡死（Not Responding）时转储所有 `python.exe` 的线程栈，输出到 `logs/stackdump.txt` | 双击，或在仓库根目录 `tools\dump_pa_stack.bat`；首次运行会自动 `pip install py-spy`。`py-spy` 是独立可执行文件，**不是** Python 模块，所以用 `py-spy dump` 而非 `python -m py_spy`；在 Windows 上通常需要管理员权限才能挂接别人的进程 |
| `probe_mt5_clock_skew.py` | 对比 MT5 服务器时钟与本机时钟，排查「正在形成的 K 线倒计时/收盘判定」偏差 | `python tools/probe_mt5_clock_skew.py [SYMBOL] [TIMEFRAME]` |
| `run_live_two_stage_smoke.py` | 用 `config/settings.json` 里的真实 Key 跑一次完整两阶段分析（会消耗额度）；只校验流程不中断，不要求校验通过 | `python tools/run_live_two_stage_smoke.py` |
| `audit_reasoning_kline.py` | 把 `records/pending/*.json` 里模型的推理文本与 prompt 里的 K 线表逐条对照，抽查「引用的 K 线是否真实存在」 | `python tools/audit_reasoning_kline.py` |
| `_inspect_pending.py` | 统计 `records/pending` 的重试次数、失败分布与最终去向 | `python tools/_inspect_pending.py` |
| `_scan_pending_retries.py` | 只扫 `records/pending` 里的校验重试（assistant/user 往返次数与反馈内容） | `python tools/_scan_pending_retries.py` |
| `setup_git_secrets.ps1` | 安装 `.githooks/` 下的 pre-commit 泄漏拦截 | `powershell -ExecutionPolicy Bypass -File tools\setup_git_secrets.ps1` |

`_pending_order_report.txt`、`_tools_catalog.json`、`stage2_raw_sample.txt` 是历史调试输出，已被 `.gitignore` 忽略，不要提交。

## 新增脚本时的要求

1. 路径从仓库根目录推导，不写死 `E:\PA_Agent` 之类的本机路径。
2. 不读取也不打印 `config/settings.json` 里的明文 Key（日志层会脱敏，但脚本自己的 `print` 不会）。
3. 一次性任务完成后请直接删除脚本，而不是留在仓库里 —— 想保留就补进上面的表格并写清用途。