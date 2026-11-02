# 四、NAS OpenAI 只使用 GLaDOS

规则作用范围是 **NAS 源地址 + OpenAI 相关域名**，目标组为 `NAS OpenAI`。候选仅来自 GLaDOS，不混入 STT、ByWave、BWB，也不增加 DIRECT 回退。其它设备和非目标流量保留原策略。

案例验收时有 14 个 GLaDOS 候选；一次实际请求链为 NAS → `NAS OpenAI` → GLaDOS 日本节点 → `api.openai.com`，携带现有 Key 的 `/v1/models` 返回 HTTP 200。节点数量与选中节点是当时快照，不写死为后续要求。

## 原生 Mihomo 模板

`templates/mihomo-nas-openai.fragment.yaml` 是合并片段，不能覆盖整份网关配置。示例使用单独的 `glados-only` file provider，它的输入文件必须只含 GLaDOS 节点；其它机场不能进入该 provider。组显式设置 `empty-fallback: REJECT`，缺失或空 provider 时拒绝请求，不回退默认直连。部署前核对核心支持该字段；案例核心的隔离空 provider 测试实际选中了 REJECT。[13]

它包含 9 条后缀规则和 12 条精确域名规则，均限定示例 NAS 地址 `192.0.2.10/32`。[9][10]

```yaml
# 示例：放在通用 AI、下载和 NAS 直连规则之前
- AND,((SRC-IP-CIDR,192.0.2.10/32),(DOMAIN-SUFFIX,openai.com)),NAS OpenAI
```

规则从上到下匹配；只写 `DOMAIN-SUFFIX,openai.com,...` 会影响所有客户端。仅在规则尾部追加也可能被此前的通用或直连规则截走。[9]

provider 的无 Key 健康检查使用 `/v1/models` 并期待 401；它用于检查可达性，不能证明 API Key 有效或所有模型调用可用。真实 API 鉴权成功需从 NAS 另测 200，不输出 Key 和返回的模型列表。探测配置显式写在 provider 的 `health-check` 中，使用候选归属与探测结果分别验收。[14]

## 既有自动生成网关的持久化

本案例网关有自定义 `mihomo-policy-overlay` 和 capabilities，不是原生 Mihomo 自带功能。`templates/client-route.example.json` 展示该扩展的输入契约，普通 Mihomo 不能直接读取它。

扩展在生成时从现有 AI 父组中按 `measurement.accounts` 筛选 GLaDOS 节点，继承健康检查，剥离混合 provider 引用，再生成精确候选和 NAS 专用规则。空候选拒绝生成，保留上次有效配置；运行期空组也显式 REJECT，不补入其它机场。重复生成、撤销 profile 与错误 ownership metadata 均有本地验证。此仓库不捆绑整个网关项目，普通安装使用上面的原生片段，并把片段合入自己的订阅生成源。

部署过程：备份当前配置/能力清单/生成器 → 生成私有候选 → 比较其它规则及组未变 → `mihomo -t` → 持有订阅与维护锁切换 → 控制器热重载 → 回读候选归属、优先级与真实 NAS 连接链 → 用已安装生成器重新生成并比较。只改最终 config.yaml、忽略生成源，会在下次订阅刷新时丢失规则。

域名依据当前 [OpenAI 网络建议][10]，后缀覆盖其下域名，外部服务保持精确匹配。不能据此保证未来新增的所有域名；OpenAI 调整依赖时需更新列表并重验。未对 14 个候选做长期稳定性或全模型验收。

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
