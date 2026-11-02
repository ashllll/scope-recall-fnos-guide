# 三、Mac Codex 与 DSH 接入

Mac 是远程客户端，模型 Key 和共享记忆库在 NAS。两个客户端分别拥有 client JSON、token 和 state 目录；它们访问两个 NAS 入口，来源分别标记 `mac-codex`、`mac-dsh`。[4]

## 准备 Mac token（NAS 初始化前）

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

## 安装远程适配器（NAS 启动后）

先备份现有 Codex/DSH 注册与插件目录，备份保存在本机私有目录。使用远程安装器，不用本地 `apply-install` 创建另一份记忆库：

```sh
SR_PY="$HOME/.local/share/scope-recall/venv/bin/python"
"$SR_PY" -m scope_recall.adapters.codex.remote_client install   --config "$HOME/.local/share/scope-recall/clients/codex/client.json"   --plugin-dir "$HOME/.local/share/scope-recall/marketplace/plugins/scope-recall"

# 等 DSH 的活跃任务结束并关闭对应 profile；路径必须是实际 DSH_HOME
"$SR_PY" -m scope_recall.adapters.codex.remote_client install   --config "$HOME/.local/share/scope-recall/clients/dsh/client.json"   --plugin-dir "$HOME/.dsh"
```

Codex 生成插件后，还需将它加入 personal marketplace、安装启用并信任实际 Hook 内容；案例插件标识为 `scope-recall@scope-recall-local`。根据当前 `codex plugin marketplace --help`、`codex plugin add --help` 与上游说明配置 marketplace manifest；不要把生成插件目录误当成已注册的 marketplace。[4]

DSH 的 `--plugin-dir` 是现有 DSH_HOME，安装器合并原有注册；检查 `cordis.patch.yml` 与插件加载状态，保留其它 MCP/插件。注册文件、生成的 MCP 配置和备份可能含访问 token，目录 `700`、文件 `600`，不入 Git。

在宿主活跃任务结束后重载 Codex/DSH。如果使用 DSH 桌面验收桥，测试工作区必须已在桥的允许范围内；案例只加入一个明确测试目录，没有扩大到整个家目录。其它部署无需为本指南自动修改桥授权。

## 真实验收

在 Codex 新会话中写入一条不敏感的测试事实，再从 DSH 新会话召回并检查来源；反向再做一次。核对真实原生 Hook 捕获、队列完成与 MCP 召回。仅用外部脚本调用 MCP 成功，不足以证明宿主对话被自动捕获。

日常可以问：“用 Scope Recall 回忆：Docker/配置和记忆/文件各放在哪个存储空间？请列出来源。”模型推断出的 `proposed` 不是确认事实，应检查原始来源。未自动导入既有 Codex 内置记忆，未自动扫描 NAS 全部文件。[1][7]

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
