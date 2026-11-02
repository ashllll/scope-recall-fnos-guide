# Scope Recall 飞牛部署全流程

版本：1.0 · 核对日期：2026-11-02 · 参考上游：3.17.0

配置与 Docker 在空间 3，记忆与文件在空间 1；Mac Codex/DSH 共享记忆；NAS OpenAI 只走 GLaDOS。

[交互部署图](deployment.html) · [仓库首页](../README.md)


## 一、前提与存储规划

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

## 二、NAS Docker 部署

### 部署输入与三个容器

将 `deploy/` 内明确需要的文件复制到 NAS 项目目录；将模板复制到私有 `config/` 后填写。真实 `.env`、Key、token 和配置不回传 GitHub。

```sh
## 在 NAS 项目目录执行；先按本机路径、UID/GID、IP 修改 example.env
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

### 凭据、入口与初始化

1. 将 `templates/model.example.env` 复制为 `config/model.env`，在本机隐藏输入框或私密编辑器中填入已有 OpenAI Key，权限设为 `600`。Key 只存在 NAS 文件中，由 `--env-file` 读取，不放入 Compose environment。
2. 先完成下一章的“准备 Mac token”。将两个摘要、NAS 私网 listen、端口分别填入 `config/entries-public.json`，结构见模板。服务端仅保存摘要，实际 token 留在 Mac；不要把本机填好的文件提交。
3. 先完成 GLaDOS 路由，再做模型连通与校准。案例使用 `text-embedding-3-small`（1536 维）与 `gpt-6-luna`；先核对账号可用模型及官方当期价格。`bootstrap-3.17.py` 中模型、价格、月额度和维度是本次案例参数，需在第一次初始化前审查，不能当成普适的计费信息。
4. 以下校准会调用 embedding API，并产生费用；只发送脚本中的合成样本，输出不含 Key 或向量。发布版脚本使用上游 `encode_embedding_text` 对 document/query 分别编码，比较配对正样本与所有交叉负样本。它生成 `config/embedding-check.json`，仅用于初始阈值，四组样本不证明广泛检索质量。该编码路径通过离线回归，发布整理没有重新调用付费 API，也没有改动既有库的阈值。

```sh
## 首次初始化只挂两个目录；shared-runtime.json 尚未生成，不能提前挂它。
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

### 启动和日常运行

确认 `shared-runtime.json` 是已有普通文件、入口配置及 Key 为部署 UID 可读，再启动：

```sh
docker compose up -d
docker compose ps
docker compose logs --tail 50 worker
```

日志仅本地检查，不上传原始会话或凭据。worker 运行上游有界批次，每批结束后等待 30 秒；容器终止信号会转发给子进程。Docker 承担重启和调度，未使用 `scope-recall autostart` 注册宿主服务；Linux 的 `autostart enable` 本身也不等于安装定时器。[8]

飞牛界面进入 **Docker → 容器**，搜索 `scope-recall`。这三个是协议入口与后台服务，没有常驻管理网页，也不是另一个飞牛应用商店插件。

## 三、Mac Codex 与 DSH 接入

Mac 是远程客户端，模型 Key 和共享记忆库在 NAS。两个客户端分别拥有 client JSON、token 和 state 目录；它们访问两个 NAS 入口，来源分别标记 `mac-codex`、`mac-dsh`。[4]

### 准备 Mac token（NAS 初始化前）

在 Mac 创建独立 venv，安装与 NAS 相同的版本；当前案例为 3.17.0：

```sh
python3 -m venv "$HOME/.local/share/scope-recall/venv"
SR_PY="$HOME/.local/share/scope-recall/venv/bin/python"
"$SR_PY" -m pip install 'hermes-scope-recall[codex]==3.17.0'
mkdir -p "$HOME/.local/share/scope-recall/clients/codex" "$HOME/.local/share/scope-recall/clients/dsh"
chmod 700 "$HOME/.local/share/scope-recall/clients" "$HOME/.local/share/scope-recall/clients/"{codex,dsh}
```

按 `templates/client-codex.example.json` / `client-dsh.example.json` 创建各自的 `client.json`；替换 NAS 私网地址、端口和全部绝对路径。JSON 内不会展开 `$HOME`，必须填入实际路径。client 文件设为 `600`。

```sh
"$SR_PY" -m scope_recall.adapters.codex.remote_client token   --config "$HOME/.local/share/scope-recall/clients/codex/client.json"
"$SR_PY" -m scope_recall.adapters.codex.remote_client token   --config "$HOME/.local/share/scope-recall/clients/dsh/client.json"
```

命令在 Mac 创建 token 文件，并输出 `token_sha256`；将摘要填入 NAS 私有 `entries-public.json`。不要把 token 本身拷入文档。已有 token 会复用，不是自动轮换。[4]

### 安装远程适配器（NAS 启动后）

先备份现有 Codex/DSH 注册与插件目录，备份保存在本机私有目录。使用远程安装器，不用本地 `apply-install` 创建另一份记忆库：

```sh
SR_PY="$HOME/.local/share/scope-recall/venv/bin/python"
"$SR_PY" -m scope_recall.adapters.codex.remote_client install   --config "$HOME/.local/share/scope-recall/clients/codex/client.json"   --plugin-dir "$HOME/.local/share/scope-recall/marketplace/plugins/scope-recall"

## 等 DSH 的活跃任务结束并关闭对应 profile；路径必须是实际 DSH_HOME
"$SR_PY" -m scope_recall.adapters.codex.remote_client install   --config "$HOME/.local/share/scope-recall/clients/dsh/client.json"   --plugin-dir "$HOME/.dsh"
```

Codex 生成插件后，还需将它加入 personal marketplace、安装启用并信任实际 Hook 内容；案例插件标识为 `scope-recall@scope-recall-local`。根据当前 `codex plugin marketplace --help`、`codex plugin add --help` 与上游说明配置 marketplace manifest；不要把生成插件目录误当成已注册的 marketplace。[4]

DSH 的 `--plugin-dir` 是现有 DSH_HOME，安装器合并原有注册；检查 `cordis.patch.yml` 与插件加载状态，保留其它 MCP/插件。注册文件、生成的 MCP 配置和备份可能含访问 token，目录 `700`、文件 `600`，不入 Git。

在宿主活跃任务结束后重载 Codex/DSH。如果使用 DSH 桌面验收桥，测试工作区必须已在桥的允许范围内；案例只加入一个明确测试目录，没有扩大到整个家目录。其它部署无需为本指南自动修改桥授权。

### 真实验收

在 Codex 新会话中写入一条不敏感的测试事实，再从 DSH 新会话召回并检查来源；反向再做一次。核对真实原生 Hook 捕获、队列完成与 MCP 召回。仅用外部脚本调用 MCP 成功，不足以证明宿主对话被自动捕获。

日常可以问：“用 Scope Recall 回忆：Docker/配置和记忆/文件各放在哪个存储空间？请列出来源。”模型推断出的 `proposed` 不是确认事实，应检查原始来源。未自动导入既有 Codex 内置记忆，未自动扫描 NAS 全部文件。[1][7]

## 四、NAS OpenAI 只使用 GLaDOS

规则作用范围是 **NAS 源地址 + OpenAI 相关域名**，目标组为 `NAS OpenAI`。候选仅来自 GLaDOS，不混入 STT、ByWave、BWB，也不增加 DIRECT 回退。其它设备和非目标流量保留原策略。

案例验收时有 14 个 GLaDOS 候选；一次实际请求链为 NAS → `NAS OpenAI` → GLaDOS 日本节点 → `api.openai.com`，携带现有 Key 的 `/v1/models` 返回 HTTP 200。节点数量与选中节点是当时快照，不写死为后续要求。

### 原生 Mihomo 模板

`templates/mihomo-nas-openai.fragment.yaml` 是合并片段，不能覆盖整份网关配置。示例使用单独的 `glados-only` file provider，它的输入文件必须只含 GLaDOS 节点；其它机场不能进入该 provider。组显式设置 `empty-fallback: REJECT`，缺失或空 provider 时拒绝请求，不回退默认直连。部署前核对核心支持该字段；案例核心的隔离空 provider 测试实际选中了 REJECT。[13]

它包含 9 条后缀规则和 12 条精确域名规则，均限定示例 NAS 地址 `192.0.2.10/32`。[9][10]

```yaml
## 示例：放在通用 AI、下载和 NAS 直连规则之前
- AND,((SRC-IP-CIDR,192.0.2.10/32),(DOMAIN-SUFFIX,openai.com)),NAS OpenAI
```

规则从上到下匹配；只写 `DOMAIN-SUFFIX,openai.com,...` 会影响所有客户端。仅在规则尾部追加也可能被此前的通用或直连规则截走。[9]

provider 的无 Key 健康检查使用 `/v1/models` 并期待 401；它用于检查可达性，不能证明 API Key 有效或所有模型调用可用。真实 API 鉴权成功需从 NAS 另测 200，不输出 Key 和返回的模型列表。探测配置显式写在 provider 的 `health-check` 中，使用候选归属与探测结果分别验收。[14]

### 既有自动生成网关的持久化

本案例网关有自定义 `mihomo-policy-overlay` 和 capabilities，不是原生 Mihomo 自带功能。`templates/client-route.example.json` 展示该扩展的输入契约，普通 Mihomo 不能直接读取它。

扩展在生成时从现有 AI 父组中按 `measurement.accounts` 筛选 GLaDOS 节点，继承健康检查，剥离混合 provider 引用，再生成精确候选和 NAS 专用规则。空候选拒绝生成，保留上次有效配置；运行期空组也显式 REJECT，不补入其它机场。重复生成、撤销 profile 与错误 ownership metadata 均有本地验证。此仓库不捆绑整个网关项目，普通安装使用上面的原生片段，并把片段合入自己的订阅生成源。

部署过程：备份当前配置/能力清单/生成器 → 生成私有候选 → 比较其它规则及组未变 → `mihomo -t` → 持有订阅与维护锁切换 → 控制器热重载 → 回读候选归属、优先级与真实 NAS 连接链 → 用已安装生成器重新生成并比较。只改最终 config.yaml、忽略生成源，会在下次订阅刷新时丢失规则。

域名依据当前 [OpenAI 网络建议][10]，后缀覆盖其下域名，外部服务保持精确匹配。不能据此保证未来新增的所有域名；OpenAI 调整依赖时需更新列表并重验。未对 14 个候选做长期稳定性或全模型验收。

## 五、备份、版本检查与升级

### 日常控制与备份

在 NAS 部署目录执行 `docker compose ps` 查看状态；`docker compose stop worker` 暂停后台模型处理，`docker compose start worker` 恢复。停止/启动全部现有容器用 `docker compose stop` / `start`。不要用 bootstrap 操作已有库。

备份要停止两个入口和 worker，以释放共享 store 锁；案例中在线备份曾返回 `owned_lock`。以下是 3.17.0 手工备份命令，退出时恢复现有服务：

```sh
(
  set -e
  trap 'docker compose start' EXIT
  docker compose stop
  archive="/data/backups/scope-recall-$(date +%Y%m%d-%H%M%S).zip"
  docker compose run --rm --no-deps worker scope-recall backup create     --root /data/shared --output "$archive" --with-vectors
  docker compose run --rm --no-deps worker scope-recall backup verify     --bundle "$archive" --temp-restore-check
)
```

不要覆盖旧备份；需要时通过 `--mirror` 指定当前 deletion mirror，核对删除记录一致性。临时恢复检查与真正生产恢复不同。案例已通过含向量备份、SQLite quick_check 和临时恢复，但初始无删除事件时报告 `deletion_mirror_lag`，没有完成删除后的生产恢复验收。[11]

model.env 在空间 3，不放入共享数据资源树；备份包未加密，不能混入 Key/token。配置应单独保存在仅本人可访问的私有备份目录。空间 1 上同机备份不是独立灾备。本案例没有自动备份计划，版本检查也不是备份计划。

### 自动检查、通知、确认后升级

`release_check.py` 从 GitHub API 读取最多最近 100 条 release，选数值版本最高的正式三段版本；忽略草稿、预发布和无效 tag，保留真实 tag 链接，不建议降级。它读部署 `.env`，失败返回 `update_available: null` 和非零退出码，不冒充“已经最新”。

```sh
python3 scripts/release_check.py --env-file deploy/.env
```

案例中的 Codex heartbeat 每天 **Asia/Shanghai 09:00** 检查。定时执行还只读核对 NAS 三个容器的真实镜像/包版本；`.env` 可能是计划值，不等于正在运行的版本。有新正式版、待升级版本改变、检查失败或恢复才通知，同一状态不重复打扰。该自动化依赖 Mac Codex 运行环境，克隆仓库不会安装它。参考提示词见 `templates/release-watch.md`。

### 用户确认明确版本后的完整顺序

1. **审查目标。** 重新检查 GitHub release、包是否发布、Python/依赖、配置默认值、schema、embedding space、删除镜像与恢复兼容性。读取目标版本文档和 `--help`，不能把 3.17 的内部 API 当成未来稳定接口。
2. **备份两端配置。** Mac 备份 clients、marketplace、DSH 插件与注册；NAS 备份空间 3 的 config、Compose、Dockerfile、`.env`。保存当前镜像 ID、实际包版本与权限。备份私密文件不进入 GitHub。
3. **暂停写入。** 等活跃对话/维护结束，停止三个容器；使用升级前运行版本完成新的含向量备份、manifest、SQLite 和删除镜像核对。不能用初始安装备份代替。
4. **固定构建输入。** 将 Mac 部署副本 `.env` 的 `SCOPE_RECALL_VERSION` 改为已确认版本；按明确文件清单同步 NAS，不覆盖 model.env、入口 token 或未知文件。再次核对空间 3/1 映射。
5. **构建候选。** `docker compose config --quiet`，再 `docker compose build`；核对包版本、镜像标签、权限和挂载。构建失败不启动候选。
6. **兼容迁移。** 只执行上游目标版本明确支持的 schema/配置迁移；核实它生成的 snapshot。不要改数据库表或删除镜像来绕过兼容检查，不重新 bootstrap。
7. **更新 Mac 两端。** 将远程 venv 更新到同一目标版本，重跑目标版本的 `remote_client install`。Codex 检查 marketplace 缓存、启用与 Hook 信任；DSH 合并现有注册。核对 client token、URL、entry 身份与权限。
8. **重载与重建。** 等宿主任务结束再重载 Codex/DSH；NAS 执行 `docker compose up -d --force-recreate`。只执行 `start` 会启动旧容器，不能代替重建。
9. **完整验收。** 实际镜像/包版本、入口健康/鉴权、旧记忆召回、两端新会话捕获与双向来源召回、worker 新任务、数据库/向量/删除镜像一致性、路径及应用额度；写入真实验证结果。
10. **保留回退材料。** 验收后保留旧镜像、配置和备份；清理另行决定，检查器不会删除它们。

若失败发生在任何迁移或新写入前，可在确认库未变后恢复旧配置/版本并以旧镜像重建。若 schema 或新写入已改变，不得只换回旧镜像；暂停写入，保留较新数据和删除镜像，按目标版本支持的 restore 流程先预览，再决定恢复到新 root、重绑定入口与恢复服务。恢复可能影响备份后的新写入，必须明确核对。后续定时检查发现计划版本与实际版本不一致时应报差异。[11][12]

## 六、验收结果与边界

本表是 2026-11-02 的既有部署验收摘要，去掉了真实 IP、账号路径、凭据、会话内容和原始日志。它不声称任意克隆环境已经通过这些验证，也不代表长期稳定性保证。

| 项目 | 结果 |
|---|---|
| Docker 根目录、配置、数据挂载 | 空间 3 / 空间 1 分离，三容器启动 |
| 入口鉴权 | 正确 token HTTP 200；无 token 401 |
| Codex 原生插件 | 真实新会话 Hook 捕获与原生 MCP 召回通过 |
| DSH 原生插件 | 真实对话完成；自动捕获队列 backlog 0、dropped 0 |
| 双向记忆来源 | 两端能分别读到另一入口的原始来源与回复 |
| 模型链路 | 嵌入与整理成功；应用内共享预算配置生效 |
| 短时容器重启 | 健康检查与跨入口召回通过 |
| 备份 | 含向量、SQLite 检查、临时恢复/绑定检查通过；保留 mirror 告警边界 |
| NAS OpenAI 分流 | 21 条源地址规则、14 个 GLaDOS 候选；真实 API 200 |
| 网关配置再生成 | 与生效配置语义一致，Mihomo 核心校验通过 |
| 更新输入 | Mac/NAS 文件校验一致；运行配置等价；容器未重启，仍为 3.17.0 |
| 版本检查器 | 草稿/预发布过滤、数值比较、禁止降级、失败状态与 tag 链接测试通过 |

### 仍需注意的行为

- 显式 MCP recall 的上游查询窗口较短，冷 embedding 偶尔超时并回退词法检索；曾见 `vector_unavailable`。最新双入口召回通过不等于该问题已根治。
- 独立 MCP 会话可能报告 `mcp_session_is_not_codex_conversation_id` / DSH 同类提示；这与已验收的原生 Hook 捕获是不同能力。
- 原部署的少量裸文本合成样本只证明嵌入链路可用，不能证明真实 document/query 检索阈值准确；发布版校准改为上游实际编码并补离线回归，但未对现网阈值重新校准；`proposed` 事实应对照来源。
- NAS 端 `doctor` 的宿主注册或 autostart 状态不代表 Mac 插件状态。容器由 Docker 管理，宿主插件另验。
- 未完成 NAS 整机重启、长时负载、完整权限隔离、纠正/删除流程、生产库覆盖恢复和断网恢复的全部演练。

本仓库发布时对脚本语法、版本检查单测、文档合并/本地链接、模板、秘密扫描与交互图做本地检查。现网安装结果和仓库可移植模板的验证范围分别记录，不用“构建通过”代替真实宿主/设备验收。

## 参考资料

核对日期：2026-11-02；上游版本基线为 3.17.0，后续升级重新核对目标版本。

1. [项目说明](https://github.com/410979729/scope-recall-hermes)
2. [安装与依赖](https://github.com/410979729/scope-recall-hermes/blob/v3.17.0/docs/install.md)
3. [SQLite WAL](https://www.sqlite.org/wal.html)
4. [远程入口](https://github.com/410979729/scope-recall-hermes/blob/v3.17.0/docs/remote-entries.md)
5. [Docker bind mounts](https://docs.docker.com/engine/storage/bind-mounts/)
6. [Docker host network](https://docs.docker.com/engine/network/drivers/host/)
7. [共享存储](https://github.com/410979729/scope-recall-hermes/blob/v3.17.0/docs/shared-store.md)
8. [上游 autostart 实现](https://github.com/410979729/scope-recall-hermes/blob/v3.17.0/maintenance/autostart.py)
9. [Mihomo 路由规则](https://wiki.metacubex.one/config/rules/)
10. [OpenAI 网络建议](https://help.openai.com/en/articles/9247338-network-recommendations-for-chatgpt-errors-on-web-and-apps)
11. [备份与恢复](https://github.com/410979729/scope-recall-hermes/blob/v3.17.0/docs/backup-restore.md)
12. [上游版本发布](https://github.com/410979729/scope-recall-hermes/releases)

13. [Mihomo 代理组与空组行为](https://wiki.metacubex.one/config/proxy-groups/)
14. [Mihomo 代理集合健康检查](https://wiki.metacubex.one/config/proxy-providers/)

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

[13]: https://wiki.metacubex.one/config/proxy-groups/
[14]: https://wiki.metacubex.one/config/proxy-providers/
