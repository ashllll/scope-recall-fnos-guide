# Scope Recall · 飞牛 NAS 部署指南

把 Scope Recall 部署到 fnOS Docker，并让 Mac 的 **Codex 与 DSH 共享同一份记忆**。本仓库总结一套在 2026-11-02 验收的部署：**Docker 与配置放存储空间 3；记忆、来源文件、向量与用量账本放存储空间 1；NAS 的 OpenAI 流量只走 GLaDOS。**

这是一份部署指南、脱敏模板和版本检查工具。它不是 Scope Recall 上游，也不会安装一套网页管理后台。模板中的 `192.0.2.10`、`YOUR_*` 是占位值；初始化脚本是 3.17.0 的案例实现，需要先核对本机环境和目标版本接口。

- **完整流程**：[部署手册](docs/00-deployment-guide.md)
- **交互图**：[下载单文件 HTML](docs/deployment.html)，在本机浏览器打开；GitHub 文件页不执行其中的交互脚本。支持深浅色、节点浏览与链路动效，无需开启 GitHub Pages。
- **操作顺序**：[前提与存储](docs/01-storage.md) → [NAS Docker](docs/02-docker.md) → [Mac 客户端](docs/03-clients.md) → [GLaDOS 路由](docs/04-network.md) → [备份与升级](docs/05-operations.md)
- **验证范围**：[验收与限制](docs/06-validation.md) · [发布核对](docs/07-publication-check.md)

## 已验收的结构

| 部件 | 作用 | 位置 |
|---|---|---|
| `scope-recall-codex` | Codex 远程 Hook / MCP 入口 | Docker / 配置在空间 3 |
| `scope-recall-dsh` | DSH 远程 Hook / MCP 入口 | Docker / 配置在空间 3 |
| `scope-recall-worker` | 后台整理、嵌入及队列处理 | Docker / 配置在空间 3 |
| shared store | SQLite、来源、向量、模型用量账本 | 空间 1 |
| Mac 插件 | 原生对话捕获、MCP 召回 | Mac；每个入口单独 token |
| `NAS OpenAI` | 按 NAS 源地址与域名分流 | 树莓派透明网关；只用 GLaDOS |

## 版本策略

参考版本是 **3.17.0**，对应上游提交 `50ab2bc34c2ebe74db2583446c6514e3d59fb67e`。Compose 的版本来源是部署目录私有 `.env` 中的 `SCOPE_RECALL_VERSION`；每次升级采用明确版本便于复现，不永久固定在这一个版本。[正式版页面](https://github.com/410979729/scope-recall-hermes/releases)

```sh
python3 scripts/release_check.py --env-file deploy/.env
```

检查器只读 GitHub Releases，忽略草稿和预发布，不拉取、不构建、不安装。案例中由 Mac Codex 每天北京时间 09:00 检查并去重通知；**用户确认目标版本后才升级**。克隆本仓库不会创建该自动化；可按 [检查与通知提示词](templates/release-watch.md) 在自己的 Codex 中建立。

## 仓库内容与本地检查

`deploy/` 保存容器与初始化案例；`templates/` 保存无密钥模板；`scripts/`、`tests/` 保存版本检查与文档检查；`diagrams/` 保存可重建的图规格。真实模型 Key、token、订阅链接、NAS 地址、会话日志、记忆库和备份均不入仓库。

```sh
bash scripts/preflight.sh
```

本地 Git 钩子/上述命令是验证入口，没有配置服务端 CI。发布前另运行 Gitleaks 和已知凭据无回显匹配；不要把扫描报告或真实配置提交。

上游项目：[410979729/scope-recall-hermes](https://github.com/410979729/scope-recall-hermes)。交互图使用 Archify，版权说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
