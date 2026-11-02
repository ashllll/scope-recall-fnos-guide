# 二、NAS Docker 部署

## 部署输入与三个容器

将 `deploy/` 内明确需要的文件复制到 NAS 项目目录；将模板复制到私有 `config/` 后填写。真实 `.env`、Key、token 和配置不回传 GitHub。

```sh
# 在 NAS 项目目录执行；先按本机路径、UID/GID、IP 修改 example.env
cp example.env .env
set -a
. ./.env
set +a
mkdir -p "$CONFIG_DIR" "$DATA_DIR/shared" "$DATA_DIR/backups"
chmod 700 "$CONFIG_DIR" "$DATA_DIR/shared" "$DATA_DIR/backups"
docker compose config --quiet
docker compose build
```

`Dockerfile` 构建 `hermes-scope-recall[lancedb,codex]`，版本来自 `.env`，基础镜像固定摘要。三个容器分别为 `scope-recall-codex`、`scope-recall-dsh`、`scope-recall-worker`；使用 host 网络、非 root UID/GID、`unless-stopped`，删除所有 capabilities，并限制日志轮转。[5][6]

容器路径固定为 `/config` 和 `/data`，宿主路径由 `.env` 控制：

```text
CONFIG_DIR                     → /config
DATA_DIR                       → /data
CONFIG_DIR/shared-runtime.json → /data/shared/runtime-config.json（只读）
```

第三个挂载让共享库看到有效 runtime 配置，同时保持配置物理存放在空间 3。它是 Docker bind mount，不是符号链接。`attach --runtime-config-from` 会产生重绑定副本，修改输入模板并不会自动更新所有有效配置。[4][7]

## 凭据、入口与初始化

1. 将 `templates/model.example.env` 复制为 `config/model.env`，在本机隐藏输入框或私密编辑器中填入已有 OpenAI Key，权限设为 `600`。Key 只存在 NAS 文件中，由 `--env-file` 读取，不放入 Compose environment。
2. 先完成下一章的“准备 Mac token”。将两个摘要、NAS 私网 listen、端口分别填入 `config/entries-public.json`，结构见模板。服务端仅保存摘要，实际 token 留在 Mac；不要把本机填好的文件提交。
3. 先完成 GLaDOS 路由，再做模型连通与校准。案例使用 `text-embedding-3-small`（1536 维）与 `gpt-6-luna`；先核对账号可用模型及官方当期价格。`bootstrap-3.17.py` 中模型、价格、月额度和维度是本次案例参数，需在第一次初始化前审查，不能当成普适的计费信息。
4. 以下校准会调用 embedding API，并产生费用；只发送脚本中的合成样本，输出不含 Key 或向量。发布版脚本使用上游 `encode_embedding_text` 对 document/query 分别编码，比较配对正样本与所有交叉负样本。它生成 `config/embedding-check.json`，仅用于初始阈值，四组样本不证明广泛检索质量。该编码路径通过离线回归，发布整理没有重新调用付费 API，也没有改动既有库的阈值。

```sh
# 首次初始化只挂两个目录；shared-runtime.json 尚未生成，不能提前挂它。
docker run --rm --user "$NAS_UID:$NAS_GID" --network host   -v "$CONFIG_DIR:/config" -v "$DATA_DIR:/data" -v "$PWD:/bootstrap:ro"   "scope-recall:${SCOPE_RECALL_VERSION}-local" python /bootstrap/calibrate.py

docker run --rm --user "$NAS_UID:$NAS_GID" --network host   -v "$CONFIG_DIR:/config" -v "$DATA_DIR:/data" -v "$PWD:/bootstrap:ro"   "scope-recall:${SCOPE_RECALL_VERSION}-local" python /bootstrap/bootstrap-3.17.py
```

`bootstrap-3.17.py` 调用 3.17.0 的上游维护 API，只用于空共享库。已有 `installation.json` 时拒绝运行；部分失败也要先检查现场，不能删除数据库再重试。其有效步骤是：

- 初始化 `/data/shared`；首个 `mac-codex` 入口带入 owner scope。
- 追加 `mac-dsh`，使用 `grants_like=all` 与 `capture_like=mac-codex`，共享当时已有 owner 授权；它不是对未来所有入口的无限自动授权。
- 为每个入口配置独立远程 listen/port/token 摘要；创建同一 embedding space 的 LanceDB 向量路径。
- 将三份有效 runtime 的用量账本统一到 `/data/shared/auxiliary-budget.sqlite3`，初始化应用预算账本。
- 将 worker runtime 文件移至 `/config/shared-runtime.json`，由 Compose 在共享根的原位置只读绑定。[7]

原理对应的上游 CLI 是 `init-shared`、`attach` 和 `remote_server configure`。这份封装使用内部维护 API，未来版本必须按 release 文档复核；升级已有库时绝不重新 bootstrap。[4][7]

案例预算是每个 Asia/Shanghai 自然月 **5 美元、10,000 次模型调用**，由应用内共享账本约束；不是 OpenAI 账户总账单上限，独立校准请求也不经过该账本。

## 启动和日常运行

确认 `shared-runtime.json` 是已有普通文件、入口配置及 Key 为部署 UID 可读，再启动：

```sh
docker compose up -d
docker compose ps
docker compose logs --tail 50 worker
```

日志仅本地检查，不上传原始会话或凭据。worker 运行上游有界批次，每批结束后等待 30 秒；容器终止信号会转发给子进程。Docker 承担重启和调度，未使用 `scope-recall autostart` 注册宿主服务；Linux 的 `autostart enable` 本身也不等于安装定时器。[8]

飞牛界面进入 **Docker → 容器**，搜索 `scope-recall`。这三个是协议入口与后台服务，没有常驻管理网页，也不是另一个飞牛应用商店插件。

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
