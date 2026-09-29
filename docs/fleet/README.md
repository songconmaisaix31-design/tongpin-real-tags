# Orca Directory Fleet Kit

一套把“目录所有权多 Agent 开发”落到 Orca CLI、Git Worktree、机器门禁和审查证据上的仓库脚手架。

## 核心模型

```text
一个总控 Agent
  ├─ 读取全局、冻结 BASE_SHA、生成 Wave/Task DAG
  ├─ 通过 Orca Run / Task / Dispatch 派发 Worker
  ├─ 处理 question、escalation、worker_done
  └─ 验证远端 SHA 后解锁下一 Wave

目录轨 Worker
  ├─ 一轨一 Worktree / 分支 / 会话
  ├─ 只写 write_paths
  ├─ 小步 commit + push
  └─ gate 通过后发送一次 worker_done

唯一集成轨
  ├─ 从冻结契约基线建立
  ├─ 合并各远端轨道分支
  ├─ 只修改组装层与共享文件
  └─ 生成发布候选与 Release Manifest
```

一句话原则：

> **功能定义验收，目录定义写权；总控只调度，Worker 不越轨；远端 SHA 才算完成。**

完整原则见 [`PRINCIPLES.md`](PRINCIPLES.md)，本地验证记录见 [`KIT_TEST_REPORT.md`](KIT_TEST_REPORT.md)。

## 为什么使用 Wave，而不是直接依赖所有 Orca Task

本模板把 `plan.json` 作为可审查的 DAG 真相源：只有当前 Wave 的依赖全部被总控验收后，才创建并派发下一 Wave 的 Orca Task。这样可以同时做到：

- 公共契约先完成并 push；
- 后续 Worker 真正从该契约任务的远端 SHA 建立；
- Orca 运行时升级后，计划、状态和证据仍留在 Git；
- 不依赖某个实验性依赖参数才能恢复任务顺序。

Orca 负责运行时能力：Run、Task、Dispatch、Worktree、Agent 会话、消息和 Decision Gate；本模板负责目录权限、基线、波次与审查证据。

## 文件结构

```text
.agents/
  fleet.json                 # 轨道所有权、Agent 默认值、检查命令
  plans/hackathon-prize.json # 当前 Wave/Task 计划
  prompts/coordinator.md     # 总控 Agent 宪法
  prompts/worker.md          # 普通 Worker 宪法
  prompts/integrator.md      # 唯一集成者宪法
  runs/                      # 每次 Run 的状态、收件箱与证据
scripts/
  fleet.py                   # 总控自动化入口
  gate.py                    # 本地/CI 目录门禁
  worker_finish.py           # 验证 push 后发送 worker_done
  install_hooks.py           # 安装 pre-commit hook
.githooks/pre-commit         # 提交前范围门禁
.github/workflows/agent-gate.yml
AGENTS.md                    # 仓库级 Agent 规则
PRINCIPLES.md                # 八条铁律
TEST_REPORT.md               # 本模板的本地验证范围与限制
orca.yaml                    # 新 Worktree Setup Hook
```

## 0. 前提

- 项目已经是 Git 仓库，并有可访问的远端基线，例如 `origin/main`。
- Orca 正在运行，CLI 已注册，Orchestration 已启用。
- Codex、Claude Code 或你选定的 CLI Agent 已在 Orca 中可用。
- Python 3 可用；脚本没有第三方依赖。
- Git 支持 `git merge-tree --write-tree`；`fleet.py doctor` 会自动检查，这是精确验证集成 merge tree 的基础。

验证 Orca：

```bash
orca status --json
orca skills install --skill orca-cli --skill orchestration
orca skills get orchestration --full
```

## 1. 安装到项目

把本目录内容复制到仓库根目录，然后修改：

```text
.agents/fleet.json
```

至少调整：

- `project`
- `base_ref`
- 每个 `tracks.<id>.allow`
- 每个轨道的 `checks`
- 默认 Agent、模型和 setup 策略

先确保目录没有重叠：

```bash
python scripts/fleet.py validate .agents/plans/hackathon-prize.json
```

然后把这套控制面提交到基线分支并 push。**并行 Worker 启动前，控制脚本和所有权配置必须已存在于它们共同的 BASE_SHA。**

## 2. 启动唯一总控 Agent

在项目主工作区运行：

```bash
python scripts/fleet.py doctor

python scripts/fleet.py start-coordinator \
  --objective "实现某个完整功能，并保留比赛审查时间线"
```

脚本会：

1. 自动定位或注册当前仓库到 Orca；
2. 设置 Orca Repo Base Ref；
3. 创建 `fleet-control-*` Worktree；
4. 启动一个总控 Agent；
5. 注入总控权限、流程和当前目标。

总控 Agent 只写 `.agents/plans`、`.agents/runs`、`.agents/decisions` 和 `.agents/handoffs`。

## 3. 总控生成并启动计划

总控根据目标生成计划：

```bash
python scripts/fleet.py validate .agents/plans/current.json
python scripts/fleet.py launch .agents/plans/current.json
```

`launch` 会创建 Orca Run，并派发所有无依赖的初始 Wave。每个 Worker 获得：

- 逻辑任务 ID；
- 精确 `BASE_SHA`；
- 唯一轨道；
- 精确 `write_paths`；
- Acceptance；
- 检查命令；
- `gate.py init` 命令；
- Orca 注入的 Task ID 与 Dispatch ID。

## 4. 总控监督循环

等待消息：

```bash
python scripts/fleet.py inbox \
  --state .agents/runs/<RUN>/state.json \
  --wait
```

处理完 Delivery 中全部消息后，再 ACK：

```bash
python scripts/fleet.py inbox \
  --state .agents/runs/<RUN>/state.json \
  --ack <DELIVERY_ID> \
  --wait
```

收到成功的 `worker_done` 后：

```bash
python scripts/fleet.py accept \
  --state .agents/runs/<RUN>/state.json \
  --task WEB-001 \
  --branch trk-web-web-001 \
  --sha <REMOTE_SHA> \
  --outcome succeeded \
  --summary "风险详情页和测试已完成" \
  --advance
```

`accept` 会从远端拉取该分支并验证：

- SHA 与远端分支一致；
- 普通 Worker 的变更只在轨道 allowlist 和任务 `write_paths`；
- 普通 Worker 的每个提交含 `[WEB-001]`；
- 集成轨只合入计划中已验收的精确依赖 SHA；
- 每个集成合并都是干净的双亲 `--no-ff` merge，且 merge tree 可由 Git 自动重算；
- 集成第一父链只在 integration 所有路径写入，并且提交都含 `[INT-001]`；
- 验收后释放或保留 Worker；
- 依赖满足时自动派发下一 Wave。

## 5. Worker 工作流

Worker 的第一条命令由 Task Prompt 自动生成，形如：

```bash
python scripts/gate.py init \
  --track web \
  --task WEB-001 \
  --base <BASE_SHA> \
  --write-path "apps/web/**" \
  --write-path "packages/ui/**"

python scripts/gate.py check --preflight
```

开发过程中：

```bash
python scripts/gate.py check --run-checks
git add apps/web packages/ui
git commit -m "feat(web): add risk detail page [WEB-001]"
git push -u origin HEAD
```

最终由 `worker_finish.py` 做最后一道验收并发送一次 `worker_done`：

```bash
python scripts/worker_finish.py \
  --logical-task WEB-001 \
  --task-id task_xxx \
  --dispatch-id dispatch_xxx \
  --base <BASE_SHA> \
  --outcome succeeded \
  --summary "页面、状态与组件测试已完成"
```

脚本会拒绝以下“假完成”：

- 修改越界；
- 工作区不干净；
- 提交缺任务 ID；
- 检查失败；
- 分支未设置 upstream；
- HEAD 未完全 push；
- 同一 Dispatch 重复发送 `worker_done`。

## 6. 集成与归档

集成轨只在所有依赖轨道被总控验收后启动。它从冻结契约基线创建，并收到依赖分支与 SHA 清单。每个依赖必须精确 `git merge --no-ff`，任何冲突都中止；组装适配只能在干净合并后的 integration 所有路径内另建提交。

全部任务完成后：

```bash
python scripts/fleet.py finalize \
  --state .agents/runs/<RUN>/state.json
```

输出：

```text
.agents/runs/<RUN>/STATUS.md
.agents/runs/<RUN>/RELEASE_MANIFEST.json
.agents/runs/<RUN>/evidence/*.json
```

这些文件把目标、Wave、Orca Run/Task/Dispatch、分支、SHA、验收和发布候选串成完整证据链。

## 推荐的轨道划分

| 轨道 | 所有权 | 禁止事项 |
|---|---|---|
| control | 计划、运行状态、决策、Handoff | 写业务代码 |
| architecture | API、Schema、ABI、事件契约 | 写消费者实现 |
| web | 前端与 UI 包 | 改 API、锁文件、部署 |
| api | 后端服务 | 改 Web、契约、根配置 |
| qa | E2E、Fixture、验收脚本 | 直接修业务实现 |
| integration | 组装层、共享根文件、发布 | 深入重写 Worker 内部代码 |
| automation | Fleet 脚本、Hook、CI | 与业务功能混改 |

## 运行纪律

- 一个 Run 对应一个清晰目标或开发 Epoch。
- 一个并行 Wave 中，一个轨道最多一个写任务。
- 同一轨道的后续任务必须串行复用轨道，不能同时开两个写入者。
- 契约变化后停止当前并行派发，先建立并验收新基线。
- Worker 只通过 Orca 消息请求跨轨工作。
- 已 push 的历史不做美化；修复用新提交或 `revert`。
- CI 是最终门禁，本地 Hook 只是提前反馈。
