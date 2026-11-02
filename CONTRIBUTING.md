# 参与贡献

感谢你对 PA Agent 的关注。本项目欢迎 Issue 与 Pull Request。

## 开发环境

1. Windows 10/11，Python 3.11+
2. 安装 MetaTrader 5 并登录（用于真实 K 线联调）
3. 克隆仓库后：

   ```cmd
   python -m venv .venv
   .venv\Scripts\activate
   pip install -e ".[dev]"
   copy config\settings.example.json config\settings.json
   ```

4. 在 GUI **设置** 中配置 API Key，或仅跑不依赖网络的测试。

## 提交代码前

```cmd
pytest -m "not live" --ignore=tests/e2e
black pa_agent tests tools
ruff check pa_agent tests tools
```

- `-m "not live"`：排除需要真实 API Key 的用例；`--ignore=tests/e2e`：e2e 会驱动 Qt 事件循环，请单独跑
  `pytest tests/e2e`。
- 每次提交前请跑一遍 `black`：仓库已统一为 black 格式（100 列），CI 不检查格式，混入未格式化的改动
  会让后续 diff 里夹带大量无关换行。
- `ruff check` 目前仍有约 200 条需要人工判断的历史问题（延迟导入、可合并 if 等），新代码请勿新增。

## 请勿提交

- `config/settings.json`、`config/exception_state.json`
- `logs/`、`records/pending/`、`experience/` 下的运行数据
- 任何 API Key、`.env`、私钥文件

启用本地 pre-commit 钩子（提交前拦截明文密钥）：

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup_git_secrets.ps1
```

钩子脚本在 `.githooks/pre-commit`，会拦截 `api_key`、`sk-`、`Bearer`、`/hook/` 等形态的明文；夹具与占位符（`tests/`、`docs/`、`*.example.*`）会被跳过。

## Pull Request 建议

- 一个 PR 聚焦一类改动（功能 / 修复 / 文档）
- 说明动机与测试方式
- 若改 JSON schema、提示词或路由，请补充或更新 `tests/` 中相关用例

## 问题反馈

- Bug：附上日志片段（`logs/pa_agent.log`）、复现步骤、品种/周期
- 功能建议：说明使用场景与期望行为

讨论与交流也可加入 README 中的 QQ 群。
