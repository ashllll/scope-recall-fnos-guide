# 一、前提与存储规划

本案例基于 fnOS Linux/x86_64、Docker 28.5.2、Compose 2.40.3，容器内 Python 3.13，Mac 转发环境 Python 3.12。其它系统/架构应重新验证依赖轮子、挂载和宿主插件。上游包名是 `hermes-scope-recall`，Python import 是 `scope_recall`。[1][2]

| 内容 | 案例布局 | 存储空间 |
|---|---|---|
| Docker 镜像、容器层 | `/vol3/docker` | 3 |
| Compose、Dockerfile、运维脚本 | `/vol3/1000/docker/scope-recall/` | 3 |
| Key、入口配置、共享 runtime 配置 | 上述目录的 `config/` | 3 |
| SQLite、来源、向量、共享用量账本 | `/vol1/1000/scope-recall/shared/` | 1 |
| 备份 | `/vol1/1000/scope-recall/backups/` | 1 |

路径是案例值，不能只凭卷编号判断物理盘。部署前在 NAS 检查：

```sh
docker info --format '{{.DockerRootDir}}'
findmnt -T /vol3
findmnt -T /vol1
id
```

确认空间 1 与 3 都是预期的本地可写存储，DockerRootDir 确实在空间 3；本指南不自动迁移已有 Docker 根目录。按 NAS 实际 UID/GID 填写 `deploy/example.env`，复制为部署目录 `.env`。创建 config/shared/backups 后，只调整这几个专用目录的权限，避免更改整卷所有权。

Mac 上编辑、维护 GitHub 仓库；NAS 只接收明确部署文件。记忆库由 NAS 本机访问，Mac 通过远程入口读写，不经 SMB 直接打开 SQLite/WAL。[3]

本仓库的示例 IP `192.0.2.10` 必须替换成实际私网 NAS 地址，并同步 `NAS_LISTEN_IP`、两份 Mac client JSON、服务端 listen 和网关的 NAS 源地址规则。入口绑定私网地址，避免暴露到公网；示例 HTTP 用于受信私网或加密隧道。服务端 token 鉴权不等于传输加密。[4]

先确认 NAS DNS 与默认路由能进入既有树莓派透明网关；仅加入 Mihomo 规则不会自动修改交换机、路由器或 NAS 的网关。后续从 NAS 实测连接，而不是只在 Mac 上测试。

[1]: https://github.com/410979729/scope-recall-hermes
[2]: https://github.com/410979729/scope-recall-hermes/blob/v3.17.0/docs/install.md
[3]: https://www.sqlite.org/wal.html
[4]: https://github.com/410979729/scope-recall-hermes/blob/v3.17.0/docs/remote-entries.md
[5]: https://docs.docker.com/engine/storage/bind-mounts/
[6]: https://docs.docker.com/engine/network/drivers/host/
[7]: https://github.com/410979729/scope-recall-hermes/blob/v3.17.0/docs/shared-store.md
[8]: https://github.com/410979729/scope-recall-hermes/blob/v3.17.0/maintenance/autostart.py
[9]: https://wiki.metacubex.one/config/rules/
[10]: https://help.openai.com/en/articles/9247338-network-recommendations-for-chatgpt-errors-on-web-and-apps
[11]: https://github.com/410979729/scope-recall-hermes/blob/v3.17.0/docs/backup-restore.md
[12]: https://github.com/410979729/scope-recall-hermes/releases
