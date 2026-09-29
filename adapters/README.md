# 数据源适配器 — 实测状态

对 `All_API_Interfaces_2026-08-22.zip` 三份文档做的实测与修复。所有结论都来自真实请求，不是读文档推断。

## 快速开始

```bash
cp credentials.example.json credentials.json   # 已 gitignore，不会进版本库
python run_probe.py --creds                    # 看凭证配置状态，不发请求
python run_probe.py                            # 跑全部，缺凭证的自动跳过
python run_probe.py github leetcode            # 只跑指定源
python run_probe.py --dump keep                # 打印原始响应，用于确认字段名
python tests/test_github_fixes.py              # 回归测试，不联网
```

## 各源状态

| 源 | 凭证 | 状态 |
|---|---|---|
| duolingo | 无需 | 已实测通过，5 标签 |
| leetcode | 无需 | 已实测通过（cn + com 双站），3-4 标签 |
| github | token 可选 | 代码已修，等 token 验证（无 token 限速 60/h） |
| steam | **需 api_key** | 端点已验真，字段结构待 key 验证 |
| keep | 需 token | `stats/records` 不存在，见下 |
| weread | 需 cookie | 文档路径全错，已换实测可用端点 |
| netease | 需自建服务 | 依赖仓库已归档，需换 fork |

## 修掉的 bug

**GitHub（4 个，原文档 V2 第 2.3 节）**

最危险的一个是静默失败：REST 响应里读的却是 GraphQL 的字段名。实跑 torvalds 对比：

```
原代码   -> primary_lang='未知'  total_stars=0       topics=[]
修复后   -> primary_lang='C'     total_stars=201500  topics=[...]
```

`primaryLanguage`/`stargazerCount`/`repositoryTopics` 在 REST 里实际叫 `language`/`stargazers_count`/`topics`。不报错、返回全 0，比崩掉更难发现。

另外三个：
- `list(set(x)[:20])` → `TypeError: 'set' object is not subscriptable`
- `datetime.utcnow() - aware_datetime` → `TypeError: can't subtract offset-naive and offset-aware`
- `fromisoformat(x.replace("Z",""))` 丢 UTC 标记 → UTC+8 下 epoch 偏早 8 小时，7 天活跃窗口边缘事件被漏算

四个都有回归测试锁定（`tests/test_github_fixes.py`），测试会先断言原写法确实出错，再断言修复后正确。

**Keep（1 个）**

`fetch_records` 用 `data.get("code") == 0` 判定成功，但 Keep 实际响应键是 `['data','errorCode','now','ok','text','version']`，没有 `code`，该分支永远为假。已统一改用 `ok`。

## Keep：`stats/records` 不存在

用 401（存在需鉴权）vs 404（不存在）做端点探测，试了 30+ 种路径变体：

```
401  /pd/v3/stats/detail          存在
401  /pd/v3/runninglog/{id}       存在
401  /pd/v3/cyclinglog/{id}       存在
401  /pd/v3/yogalog/{id}          存在      ← 文档未提
401  /pd/v3/hikinglog/{id}        存在      ← 文档未提
401  /pd/v3/traininglog/{id}      存在      ← 文档未提
404  /pd/v3/stats/records         不存在    ← 文档核心接口
```

`/pd/v2|v1|v4/stats/records`、`/pd/v3/records`、`/pd/v3/timeline`、`/pd/v3/logs` 等一律 404。

影响：`sport_primary_type`、`sport_active_time`、`sport_consecutive_weeks` 三个标签原本全靠这个接口推导，目前无数据来源。适配器已按「无 records」重构，这三个标签暂缺，`fetch()` 里有 TODO 标注。拿到 token 后跑 `--dump keep` 看 `stats/detail` 是否内嵌单次记录列表，再决定补法。

**password 加密方式**（文档列为阻塞项）：用假号码做字段校验探测得到——只传 mobile 返回 `"password required"`，补上 password 返回 `errorCode 100001 账号与密码不匹配`。服务端在做凭证比对而非报解密失败，说明明文在传输层被接受。但不排除服务端对收到值再做哈希，要确认得用真实账号试一次。至少「必须逆向 App 拿 RSA 公钥」可以从阻塞项降级。

## 微信读书：文档三处事实错误

1. **「2026 年官方推出 AI Skill」「weread-mcp 是官方 MCP Server」不成立。** npm 上该包自己的 description 写着「微信读书 MCP Server (**非官方**)」，repository 指向个人账号 `github.com/j2st1n/weread-mcp`，maintainer `rq3zs2wo`，发布于 2026-05-26。原文档整节的风险评级建立在「官方支持后风险降低」上，前提不成立。

2. **文档给的内部 API 路径是 404。** 实测：

```
404  /user/reading/statistics    文档所述，不存在
404  /note/getList               文档所述，不存在
401  /shelf/sync                 实际可用（需 cookie）
401  /readdetail                 实际可用
401  /user                       实际可用
```

`read_yearly_hours`/`read_consistency`/`read_favorite_categories` 依赖的正是那个 404 路径，文档里 `thisWeekMinutes`/`favoriteAuthors` 那段返回示例应是虚构的。

3. **MCP 模式架构错误。** 原 `WeReadAdapter` 假设 `http://localhost:3001` 上有 REST 端点，但 MCP 是 stdio 上的 JSON-RPC，不是 HTTP 服务。已删除该模式，只保留 cookie 直连。

## 网易云：依赖已归档

`Binaryify/NeteaseCloudMusicApi` 实测 `archived=true`，最后提交 2024-02-28。而文档「替代项目」一栏填的是同一个归档仓库的同一个 URL，自我循环。需换活跃 fork。

另外文档正文接口清单写 POST、Python 示例用 GET，二者不一致（已统一 POST）；文档 746 行端口 `300300` 超出合法范围，应为 3000。

## 补上的两个源

接口文档把 `DUOLINGO`/`LEETCODE` 写进了 `DataSourceType` 枚举，但 Duolingo 只有接口签名没实现，LeetCode 连调研都没有。两个都无需鉴权，实测可用，建议提到 P0。

Duolingo 一个坑：接口文档说打卡判定用 `streakData.currentStreak.endDate`，但实测连胜为 0 时 `currentStreak` 是 `null`（官方账号 duo 就是），直接取 `.endDate` 会崩，必须判空。

LeetCode 两站 schema 不同，不能共用 query：
- `.com` 用 `matchedUser(username:)`，`profile.ranking` 是标量；难度枚举 `All/Easy/Medium/Hard`（`All` 是汇总项，统计要排除否则翻倍）
- `.cn` 用 `userProfilePublicProfile(userSlug:)`，`profile.ranking` 是对象需子选择（有 `currentRating`/`currentGlobalRanking`，无 `totalRating`）；难度枚举大写 `EASY/MEDIUM/HARD`；关闭了 introspection

## 未修：保真方案的设计问题

「轻量化加密保真」这套 TLS 指纹 + 平台 HMAC 证明不了数据真实性——签名是平台用自己的私钥签自己发出的声明，对第三方等价于「我说这是真的」。它有价值，但价值是服务端审计日志，不是防伪证明，文档把它定位成 ZK-TLS 的替代品偏高了。

代码层面也是空的：`map_keep_data_to_tags` 里 `extract_tls_fingerprint(requests.Response())` 传了个刚 new 出来的空 Response，函数体直接 `return` 常量，所以白名单校验永远无条件通过。这属于产品决策范畴，等确认方向后再动。
