# API 接口可用性测试结论

## 结论

ZIP 中的接口不能整体判定为“可用”。本轮在不读取任何凭据、不执行登录/签到等副作用操作的前提下，对 37 个具体 HTTP/MCP 契约项进行了实测：

| 结果 | 数量 | 含义 |
|---|---:|---|
| `AVAILABLE` | 6 | 安全功能请求返回 2xx，响应顶层结构符合预期 |
| `AUTH_REQUIRED` | 7 | 路由可达，但需要有效认证 |
| `REQUEST_REJECTED` | 3 | 路由可达，但合成输入或缺失认证参数被拒绝 |
| `INCONCLUSIVE_SAFE_PROBE` | 1 | 只做了无副作用握手，未执行真实业务操作 |
| `ROUTE_NOT_FOUND` | 3 | 文档路径返回 404 |
| `RESOURCE_NOT_FOUND` | 2 | 合成资源不存在，不能据此否定路由本身 |
| `PREREQUISITE_MISSING` | 11 | 所需本地服务未运行，不能判第三方服务宕机 |
| `NOT_TESTED_PREREQUISITE` | 3 | 缺 MCP server 配置，未调用工具 |
| `CONTRACT_INVALID` | 1 | 文档端口超出合法 TCP 范围 |

完整逐项状态、HTTP 状态码和延迟见
[`api-interface-validation-2026-08-22.md`](api-interface-validation-2026-08-22.md)，机器可读证据见
[`api-interface-validation-2026-08-22.json`](api-interface-validation-2026-08-22.json)。

## 可以直接使用

- GitHub REST：用户资料、仓库列表、公开事件均返回 `200`，且响应结构符合契约。
- Duolingo 公共用户接口返回 `200`。
- LeetCode CN 与 COM 的只读 GraphQL 探测均返回 `200`。

GitHub REST 属于官方公开接口，适合当前 MVP。Duolingo 与 LeetCode 这里使用的是公开可访问但未在 ZIP 中形成正式官方契约的路径，能用于 Demo，但需要把上游变更风险隔离在 adapter 内。

## 路由存在，但还不能宣称业务可用

- Steam：7 条路由全部收到 HTTP 响应，结果为 `400/401/403`。官方文档要求 Web API key；未使用 key 的本轮测试只能证明路由可达，不能证明认证后字段和用户数据链路正确。
- GitHub GraphQL：返回 `403`，与官方要求认证一致。
- Keep：`stats/detail` 返回 `401`；登录接口只做 `OPTIONS`，返回 `200`。没有执行真实登录。
- WeRead：`/shelf/sync` 返回 `401`，说明该路径存在但需要认证。

## 应从当前契约移除或修正

- Keep `/pd/v3/stats/records` 返回 `404`，不能继续作为核心历史记录数据源。
- WeRead `/user/reading/statistics` 与 `/note/getList` 均返回 `404`。
- NetEase QR check 使用的 `localhost:300300` 是非法端口，应为有效的本地服务端口后再验证。
- ZIP 中假设 MCP 在 `localhost:3001` 暴露 `/reading/stats`、`/shelf`、`/notes` REST 路径；当前没有该服务，且 MCP tool 与任意本地 REST façade 不是同一契约。

Keep 的 running/cycling log 使用合成 ID `0` 时返回 `404`，这里只能标记为“资源不存在”；需要合法测试资源 ID 才能判断业务路径。

## 本地前置条件缺失

- NetEase Cloud Music 的 8 个本地接口没有服务监听，全部为 `PREREQUISITE_MISSING`。上游 `Binaryify/NeteaseCloudMusicApi` 已归档，不应继续按“活跃稳定依赖”描述。
- WeRead 三个 MCP tool 没有配置 server，因此未调用；三个假设的本地 HTTP 路径也没有服务监听。

微信读书官方域名的 Skill 页面当前返回 `200`，但 npm 的 `weread-mcp@1.0.0` 包描述明确写有“非官方”，仓库指向个人账号。官方 Skill、第三方 MCP 包和私有 HTTP API 必须分别建模。

## 安全边界与限制

- 未读取 `credentials.json`、`.env`、cookie、token、password 或 private key。
- 未执行 Keep 登录、NetEase 登录/QR 会话/签到，未执行任何 GraphQL mutation。
- TLS 校验保持开启；不跟随重定向；响应读取上限 4096 bytes；不保存原始响应正文。
- 本轮没有证明认证后的业务成功、用户私有数据字段、字段映射或速率限制表现。
- 现有 `run_probe.py` 会无条件加载凭据，并提供未脱敏 raw dump，不应拿真实凭据直接运行。

## 一手资料核对

- [GitHub GraphQL calls and authentication](https://docs.github.com/en/graphql/guides/forming-calls-with-graphql)
- [GitHub REST user endpoints](https://docs.github.com/en/rest/users/users)
- [Steamworks ISteamUser Web API](https://partner.steamgames.com/doc/webapi/ISteamUser)
- [Archived NeteaseCloudMusicApi repository](https://github.com/Binaryify/NeteaseCloudMusicApi)
- [WeRead Skill landing page](https://weread.qq.com/r/weread-skills)
- [weread-mcp package](https://www.npmjs.com/package/weread-mcp)

## 复现

```powershell
python -m unittest tests.test_endpoint_probe -v
python endpoint_probe.py --json reports\api-interface-validation-2026-08-22.json --markdown reports\api-interface-validation-2026-08-22.md
```

