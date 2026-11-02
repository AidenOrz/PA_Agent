# 安全策略

## 支持的版本

| 版本 | 支持 |
|------|------|
| 最新 `main` 分支 | 是 |
| 旧 tag / 分支 | 仅作参考，不保证修复 |

## 报告漏洞或密钥泄露

**请勿在公开 Issue 中粘贴 API Key、加密后的 `api_key_encrypted`、完整 `settings.json` 或含个人账号信息的分析记录。**

请通过以下方式私下联系维护者：

- GitHub：**Security Advisories**（仓库 → Security → Report a vulnerability），或
- QQ 群（见 README）私信维护者

报告中请尽量包含：

- 问题类型（误提交密钥、本地文件权限、依赖漏洞等）
- 影响范围与复现步骤
- 是否已在公开仓库历史中暴露密钥（如是，请说明大致时间以便协助轮换）

## 用户自查清单

1. 确认 `config/settings.json` 未被 `git add`（应被 `.gitignore` 忽略）。
2. 执行 `tools\setup_git_secrets.ps1` 启用 pre-commit 拦截。
3. 若 Key 曾进入 Git 历史：在服务商处轮换 Key，并清理 Git 历史或作废旧仓库镜像。
4. 开源 fork 时删除 `records/`、`logs/`、`experience/` 中的私人数据后再推送。

## 凭据存储位置（自查时逐一核对）

| 位置 | 内容 | 保护方式 |
|------|------|----------|
| `config/settings.json` → `provider.api_key_encrypted` | AI API Key | Windows DPAPI（仅当前用户可解），**推荐** |
| `config/settings.json` → `tushare.token` | Tushare Pro token | **明文**，与上面不一致；文件本身被 `.gitignore` 忽略 |
| `config/settings.json` → `feishu.webhook_url` / `secret` / `app_secret` | 飞书机器人凭据 | **明文**；webhook URL 里的 token 等价于凭据 |
| `config/settings.json` → `pushplus.token` | PushPlus token | **明文** |
| `logs/pa_agent.log`、崩溃日志、`records/pending/*.json` | 可能包含上述值 | 运行时脱敏（`register_settings_secrets()`），掩码为 `***` |

脱敏是**尽力而为**的兜底，不是加密：出现在非常规格式里的密钥仍可能漏出，因此不要把 `config/settings.json`、
`logs/`、`records/` 分享给他人或提交进仓库。

## 免责声明

本软件为交易分析辅助工具，不提供托管服务；安全配置（API、MT5 账户）由使用者自行负责。
