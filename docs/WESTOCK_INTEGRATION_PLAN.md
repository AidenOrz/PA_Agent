# WeStock 数据源接入计划

> 制定日期：2026-08-05
> 当前状态：实现与离线验收完成
> 依据：[数据源使用文档](../数据源使用文档.md)、WeStock skill 1.0.5、当前 `DataSource` 抽象

## 1. 目标与边界

让 PA Agent 的 K 线工作台可以选择并使用项目约定的用户版 WeStock：

```text
npx -y westock-data-skillhub@1.0.5 kline <symbol> --period <period> --limit <n> --raw
```

本阶段只接入软件当前 `DataSource` 抽象实际需要的 K 线轮询能力：连接检查、订阅、取消订阅、支持周期和最新 K 线快照。WeStock 的资金流、北向、两融、筹码等扩展命令不在本阶段伪装成行情接口，也不进行真实行情请求验收。

不修改用户配置、交易记录、日志或研究资料；不保存凭据；不把 WeStock 包下载到仓库；测试只使用 mock 的 CLI 进程结果。

## 2. 已验证事实与关键决策

- 项目文档指定用户版包为 `westock-data-skillhub@1.0.5`，CLI 使用 `kline`，通过 `--raw` 获取机器可解析结果。
- WeStock K 线周期为 `day/week/month/season/year`，代码格式为 `sh/sz/bj`、`hk`、`us` 前缀。
- 当前应用的工厂和 GUI 已有统一数据源切换流程，但配置类型、工厂注册和 UI 选择列表尚未包含 `westock`。
- 当前共享复权设置为 `qfq/hfq/none`；WeStock 映射为 `qfq/hfq`，`none` 遵循项目文档的已知兼容策略不传 `--fq`。
- CLI 依赖 Node.js >= 18；当前本机 Node 版本为 `v24.18.0`。连接阶段只检查运行时，不在启动时下载或请求行情。

## 3. 实施范围

1. 新增 `pa_agent/data/westock_source.py`。
   - 规范化 A 股、港股、美股代码和 `1d/1w/1M/3M/1y` 周期。
   - 使用结构化 JSON 解析，兼容 `data/result/rows/items` 包装、字段别名和 Markdown/日志噪声。
   - 将失败退出、超时、错误 JSON、空结果和无效 K 线统一转换为 `DataSourceTransientError`。
   - 限制请求条数为 WeStock 支持的 2000 条以内，加入短 TTL 缓存，防止 GUI 1 Hz 刷新重复启动 npx。
   - 将日期/数值转换为 `KlineBar`，按最新在前返回，并保留成交额和涨跌幅（如果返回）。
2. 更新工厂和配置类型，令 `westock` 可被创建、持久化和显示。
3. 更新 GUI 的默认品种纠正、占位提示和周期恢复逻辑，使从 MT5/TradingView 切换到 WeStock 时不会把 `XAUUSDm` 或分钟周期直接提交给 CLI。
4. 新增完全离线的单元测试，覆盖命令参数、代码/周期/复权映射、JSON 形状、CLI 错误、超时、缓存和生命周期。

## 4. 风险与取舍

- `npx` 首次执行可能下载包且耗时较长，因此连接阶段不探测包，快照阶段使用可控超时并将异常显示为数据源瞬时错误。
- WeStock 的 `kline` 是轮询历史/当前 K 线，不等同于独立实时 quote；本阶段不声称提供逐笔实时行情。
- CLI 的 raw 返回格式以文档为依据但需容错，因此解析器只接受含完整 OHLC 的结构化行，不能用默认值伪造缺失价格。
- 月线使用 `1M`，避免被项目已有的分钟周期大小写兼容逻辑误判为分钟。

## 5. 验收标准

- WeStock 工厂和配置测试通过，GUI 数据源选择列表包含 WeStock，切换时默认品种/周期有效。
- 所有新增源测试通过，且测试不会执行 `npx`、访问网络或读取真实密钥。
- `python -m compileall -q pa_agent tests` 通过；目标文件静态检查通过。
- 真实行情联调不在本阶段执行；最终说明中明确安装/网络前置条件和未覆盖范围。

## 6. 恢复点

当前最后稳定点是上一轮缺陷修复后的源码和聚焦测试。若本阶段中断，从本文件第 3 节开始核对实际文件，再运行新增 `test_westock_source.py` 和工厂测试；不要回退上一轮持久化、校验、线程或密钥安全修改。

## 7. 实际结果（2026-08-05）

- 新增 `pa_agent/data/westock_source.py`，完成 Node/npx 运行时检查、CLI K 线查询、结构化解析、代码/周期/复权映射、短缓存和错误归一化。
- `westock` 已接入配置类型、数据源工厂和 GUI 数据源选择；旧黄金品种和分钟周期会在切换/启动时迁移到有效的 A 股日线默认值。
- 新增完全 mock 的 `tests/unit/test_westock_source.py`，没有执行真实 npx 行情请求。
- WeStock、工厂、AkShare、Tushare 和设置持久化聚焦回归：`46 passed`。
- `python -m compileall -q pa_agent tests`：通过。
- 新增适配器和测试的窄范围 `ruff` 检查：通过。
- 已知非本次问题：`test_market_defaults.py::test_tv_forex_auto_probe_tries_all_forex_presets` 仍受现有 TradingView 探测列表与旧测试契约不一致影响；本任务未扩大修改。
- 真实 WeStock 联调未执行，运行时仍需要 Node.js >= 18、可用的 npx/npm 网络或本地 npm 缓存。
