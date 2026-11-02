# 五、备份、版本检查与升级

## 日常控制与备份

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

## 自动检查、通知、确认后升级

`release_check.py` 从 GitHub API 读取最多最近 100 条 release，选数值版本最高的正式三段版本；忽略草稿、预发布和无效 tag，保留真实 tag 链接，不建议降级。它读部署 `.env`，失败返回 `update_available: null` 和非零退出码，不冒充“已经最新”。

```sh
python3 scripts/release_check.py --env-file deploy/.env
```

案例中的 Codex heartbeat 每天 **Asia/Shanghai 09:00** 检查。定时执行还只读核对 NAS 三个容器的真实镜像/包版本；`.env` 可能是计划值，不等于正在运行的版本。有新正式版、待升级版本改变、检查失败或恢复才通知，同一状态不重复打扰。该自动化依赖 Mac Codex 运行环境，克隆仓库不会安装它。参考提示词见 `templates/release-watch.md`。

## 用户确认明确版本后的完整顺序

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
