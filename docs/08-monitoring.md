# 七、可视化状态面板与 Bark 通知

本仓库提供一个独立的只读状态面板。飞牛进入 **Docker → 容器 → scope-recall-monitor → 快捷访问 → 18767:8080**，浏览器即打开 `http://<NAS 私网地址>:18767/`。它显示运行指标，不展示对话正文、API Key 或入口 token，也不提供记忆修改、重启、升级按钮。

面板是本部署仓库的运维扩展，不是上游 `scope-recall ui`。后者仍是由所有者临时启动的本地记忆管理页面。面板没有独立登录，只绑定 NAS 指定的私网 IPv4，拒绝未知 Host，不开放跨域读取。只适用于受信任的局域网；不要直接转发到公网。局域网可访问者能看到来源数量、用量和运行状态。[15]

## 运行与数据位置

| 部件 | 位置与权限 |
|---|---|
| `scope-recall-monitor` | 使用现有版本的 Scope Recall 镜像；256 MiB 内存上限；不挂 Docker socket |
| `monitor.py`、`index.html`、Compose 扩展 | NAS 项目目录，空间 3 |
| `config/monitor/` | 配置、两枚入口 token 的私有副本、SendKey，空间 3；目录 700、文件 600 |
| `DATA_DIR/monitor/` | 聚合状态、告警去重记录，空间 1；目录 700 |
| shared store、backups、model.env、runtime | 监控容器只读挂载；不迁移、不修复或改写记忆库 |
| 树莓派 `scope-recall-watchdog.service` | 独立于 Docker 的 NAS 可达性探针；不修改 Mihomo 配置 |

原入口服务仍只持有 token 摘要；监控作为状态查询客户端，需要真实入口 token。不要把它们写入 environment、命令参数或公共模板。

## 在已有部署添加面板

在 Mac 克隆中编辑并核对，再将明确文件同步到 NAS。以下命令在 NAS 的 Scope Recall 项目目录执行。`CONFIG_DIR`、`DATA_DIR`、`NAS_UID`、`NAS_GID` 均取已有 `.env` 中的实际值，配置不一定在项目目录内；不要在已运行环境重新复制 example.env 覆盖真实 `.env`。

1. 同步 `deploy/compose.monitor.yaml` 和整个 `deploy/monitor/`（其中 systemd 文件供树莓派使用）。保持 `compose.yaml` 和 `.env` 原有版本、路径、UID/GID。
2. 创建 `${CONFIG_DIR}/monitor/`，目录属主设为实际 NAS_UID/NAS_GID、权限 700；将 `templates/monitor.example.json` 复制到 `${CONFIG_DIR}/monitor/monitor.json`。把 `allowed_hosts` 中的示例 IP、两个入口 URL 换成本机实际私网 IP/端口。调整阈值时同步检查页面文案。
3. 从 Mac 两个 `client.json` 指定的 `token_file` 安全复制 token 到 NAS `${CONFIG_DIR}/monitor/codex.token`、`${CONFIG_DIR}/monitor/dsh.token`。`client.json` 默认位于 `~/.local/share/scope-recall/clients/<host>/`。不要复制或打印整个客户端配置。
4. 在 NAS `${CONFIG_DIR}/monitor/serverchan.key` 私密填写 SCT 开头的 Server酱 SendKey；在 Server酱控制台把这个应用专用 Key 的通道绑定为 **Bark iOS**。本实现不接收 Bark 设备 Key 或 SC3 Key。所有私密文件设为 600，属主与 `.env` 中的 NAS_UID/NAS_GID 一致。
5. 创建空间 1 的 `${DATA_DIR}/monitor/` 目录，属主同上、权限 700。在 `.env` 保留原值并补入 `MONITOR_PORT=18767`、`COMPOSE_FILE=compose.yaml:compose.monitor.yaml`。确认还存在 `NAS_UID`、`NAS_GID`、`CONFIG_DIR`、`DATA_DIR`、`NAS_LISTEN_IP`。

```sh
docker compose config --quiet
docker compose up -d --no-deps monitor
docker compose ps
docker exec scope-recall-monitor python /monitor-app/monitor.py \
  --config /config/monitor.json --test-notification
```

成功提交会输出 `{"ok": true, "code": 0}`，不回显 SendKey 或含 Key 的 URL。还需确认 iPhone Bark 实际收到消息。上述部署不会重建三个记忆服务，也不会产生模型生成费用；监控使用已有镜像，通过只读 bind mount 加载自身源码。[16]

## 检查内容和默认阈值

| 检查 | 周期 / 异常条件 | 含义 |
|---|---|---|
| Codex、DSH 入口 | 每轮鉴权 `/health` 与 MCP `status` | 不等于 Mac 宿主插件刚刚完成捕获 |
| 队列 | 失败任务非零，或最老待处理超过 15 分钟 | 来源数量是原始记录数，不是整理后的事实数量 |
| worker | 最近完成超过 10 分钟、退出异常或 `degraded` | 普通 idle/waiting 不是进程失败；持续积压另判 |
| OpenAI | 每 15 分钟 GET `/v1/models` | 检查 DNS/TLS/网络/Key 鉴权；不证明每种模型调用都成功，不发送对话 |
| 存储 | 两个挂载所在文件系统剩余不足 10% | 配置目录空间 3、共享数据空间 1；不等同独立 Docker 根分区检查 |
| 用量 | 应用共享账本当月费用或次数达到配置额度 90% | 按 runtime 的时区、batch、额度读取；不是 OpenAI 总账单 |
| 备份 | 没有 zip 文件或最新文件超过 7 天 | 只看文件元数据，不在采样时解包验证，也不自动创建备份 |
| 采集器 | `/healthz` 的最近采样超过 240 秒 | Docker healthcheck 与外部探针能发现采集停止 |

NAS 每轮完成后等待 60 秒，网络延迟会使实际采样间隔略长；页面每 15 秒刷新缓存。队列图保留本次进程最多 120 个样本；成功告警记录最多 30 条并持久化。

每个异常分别计时，连续存在至少 120 秒才加入通知；消失至少 60 秒才从已通知集合移除。只有稳定异常集合改变时发送，保持相同状态不重复提醒。单项抖动不会推迟其他持续故障。全部已通知异常消失时发送恢复；仍有异常时发送更新后的异常集合。发送失败不会记作成功，15 分钟后重试；仍受 Server酱账户额度和通道限制。持久化记录跨容器/服务重启保留。

面板无流量时最后写入时间不变是正常情况。账本、worker 文件和 SQLite 聚合查询基于 3.17.0；升级必须重新核对上游字段。字段不兼容会显示不可读，不能把异常吞掉后显示正常。

## 树莓派外部探针

NAS 断电时自身无法发通知，所以在独立在线的树莓派运行同一脚本的 `probe` 模式。它只 GET 面板 `/healthz`，不读取记忆、模型 Key 或入口 token；另保存一份 SendKey 以发送 NAS 断联与恢复通知。NAS 与树莓派同时断电、网关无法访问通知服务或手机通道故障时仍无法实时送达。

将下列文件通过 Mac 安全传到树莓派：

```text
deploy/monitor/monitor.py                  → /opt/scope-recall-watchdog/monitor.py
deploy/monitor/scope-recall-watchdog.service → /etc/systemd/system/scope-recall-watchdog.service
templates/watchdog.example.json           → /etc/scope-recall-watchdog/config.json
私密 SendKey 文件                         → /etc/scope-recall-watchdog/serverchan.key
```

修改 config.json 的 `probe_url` 为实际面板 `/healthz`。配置目录 root 所有、700；配置和 Key 文件 root 所有、600；脚本和 unit 为 root 所有、644。不要把真实值提交。

```sh
sudo systemd-analyze verify /etc/systemd/system/scope-recall-watchdog.service
sudo systemctl daemon-reload
sudo systemctl enable --now scope-recall-watchdog.service
systemctl is-active scope-recall-watchdog.service
systemctl is-enabled scope-recall-watchdog.service
```

服务使用 DynamicUser、LoadCredential 和 StateDirectory，凭据由 systemd 提供到 `/run/credentials/scope-recall-watchdog.service/`，去重状态保存在 `/var/lib/scope-recall-watchdog/`。树莓派需要 Python 3.9+、可用时区数据库和支持这些指令的 systemd；本案例实测 Python 3.13。它不修改代理节点、规则或网关配置。[17]

## 维护、升级与验收

- 计划停 NAS / 监控前，先在树莓派 `sudo systemctl stop scope-recall-watchdog`；维护完先确认面板 `/healthz` 正常，再 `sudo systemctl start scope-recall-watchdog`。`stop` 不取消下次开机启用。不要为维护删除去重状态或提高故障阈值。
- 单独更新监控代码：在 Mac 检查、同步对应文件，`docker compose restart monitor`；树莓派同步脚本后 `sudo systemctl restart scope-recall-watchdog`。不需要更新记忆引擎镜像。
- 上游升级仍需用户确认版本，按第五章完成备份和两端验收；监控需要额外核对 worker 字段、MCP status、来源表/用量表聚合、只读挂载、告警与恢复。版本检查不是自动升级，监控也不会自动修复或重启业务。
- 验收分层：单测覆盖稳定故障/抖动/恢复/失败重试/重启去重；隔离测试状态发送模拟故障与恢复；短暂停止监控容器验证树莓派真实断联与恢复。停止监控不影响记忆的三个业务容器；不要为验收关掉生产 NAS。
- 本案例已验证飞牛快捷访问与实际页面、入口健康及队列、只读数据库统计、Server酱 `code:0` 和用户确认 iPhone 收到测试消息。停止监控容器后，树莓派成功提交失联通知；恢复监控后成功提交恢复通知。完整整机断电和长期稳定性另验。

[15]: https://github.com/410979729/scope-recall-hermes/blob/v3.17.0/docs/ui.md
[16]: https://github.com/easychen/serverchan-sdk
[17]: https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html
