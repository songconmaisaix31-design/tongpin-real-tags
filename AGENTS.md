# Repository Agent Constitution

本仓库采用 Orca CLI 管理的“目录所有权”多 Agent 开发模式。

## 最高优先级规则

1. 功能定义验收，目录定义写权限。
2. 只修改当前任务明确列出的 `write_paths`；读取其他目录不代表拥有写权限。
3. 当前会话绑定当前 Worktree、分支和轨道。所有轨道禁止 `git switch`、`git checkout`、`git rebase`、`git reset --hard`、`git push --force`；只有 integration 轨可以按其专用 Prompt 执行经过验收的 `git merge --no-ff`。
4. 需要跨轨修改时，向总控 Agent 提问或升级，不直接修改对方文件。
5. 禁止修改公共契约、根依赖、锁文件、部署配置和 CI，除非当前轨道明确拥有这些路径。
6. 禁止全仓库格式化；只格式化当前允许目录。
7. 每个可验证增量立即提交并推送。已推送历史不得改写。
8. 完成必须同时满足：范围门禁通过、要求的检查通过、工作区干净、分支已推送、HEAD 等于远端上游、发送一次 `worker_done`。

## 标准循环

```text
Preflight
→ 初始化任务上下文
→ 只在允许目录实现
→ 运行轨道检查
→ 范围门禁
→ commit
→ push
→ worker_finish.py
```

## 阻塞处理

不要猜测或越权修复。通过 Orca Orchestration 发送 `question` 或 `escalation`，说明任务、Dispatch ID、阻塞原因、责任轨道、建议变化以及是否阻塞当前交付。
