# 六、验收结果与边界

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

## 仍需注意的行为

- 显式 MCP recall 的上游查询窗口较短，冷 embedding 偶尔超时并回退词法检索；曾见 `vector_unavailable`。最新双入口召回通过不等于该问题已根治。
- 独立 MCP 会话可能报告 `mcp_session_is_not_codex_conversation_id` / DSH 同类提示；这与已验收的原生 Hook 捕获是不同能力。
- 原部署的少量裸文本合成样本只证明嵌入链路可用，不能证明真实 document/query 检索阈值准确；发布版校准改为上游实际编码并补离线回归，但未对现网阈值重新校准；`proposed` 事实应对照来源。
- NAS 端 `doctor` 的宿主注册或 autostart 状态不代表 Mac 插件状态。容器由 Docker 管理，宿主插件另验。
- 未完成 NAS 整机重启、长时负载、完整权限隔离、纠正/删除流程、生产库覆盖恢复和断网恢复的全部演练。

本仓库发布时对脚本语法、版本检查单测、文档合并/本地链接、模板、秘密扫描与交互图做本地检查。现网安装结果和仓库可移植模板的验证范围分别记录，不用“构建通过”代替真实宿主/设备验收。

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
