# Codex 正式版本检查提示词

在自己的 Codex 中创建每天 Asia/Shanghai 09:00 的当前聊天 heartbeat。把以下路径和 NAS 连接替换为自己的值；本文件不会安装自动化，也不携带 SSH/API 凭据。

> 工作目录为本指南仓库。运行 `python3 scripts/release_check.py --env-file <实际部署.env绝对路径>`，只读检查 Scope Recall GitHub 正式发布。只读核对 NAS 三个 scope-recall 容器的镜像和包版本，不能把 .env 计划版本当成运行版本。保持配置在空间3、数据在空间1。只在首次发现新正式版、待升级版本改变、检查失败或恢复时通知；状态不变保持安静，不重复提醒同一版本。可把版本、状态、检查时间和已通知版本存入本机被忽略的 evidence/release-watch-state.json。通知用中文列出实际/最新版本、官方 release 链接、重要变化与迁移事项，询问是否升级。定时任务不得更新 .env、pull/build/pip install、重启服务或迁移数据库；用户确认明确版本后，再按 docs/05-operations.md 处理。不要输出模型Key、入口token或代理订阅凭据。NAS无法访问或版本不一致时说明未核实。
