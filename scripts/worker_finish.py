#!/usr/bin/env python3
"""Verify a worker branch and send exactly one Orca worker_done message."""
from __future__ import annotations

import argparse
import json
import sys

sys.dont_write_bytecode = True

from common import (
    FleetError,
    changed_files,
    commit_subject,
    commit_subjects,
    git_branch,
    git_out,
    git_path,
    git_root,
    git_sha,
    integration_analysis,
    load_config,
    load_context,
    now,
    parse_json,
    run,
    run_checks,
    save_json,
    scope_violations,
)


def files_argument(files: list[str], limit: int = 6000) -> str:
    if not files:
        return "none"
    chunks: list[str] = []
    used = 0
    for index, path in enumerate(files):
        addition = ("," if chunks else "") + path
        if used + len(addition) > limit:
            chunks.append(f",...+{len(files) - index}-more")
            break
        chunks.append(addition)
        used += len(addition)
    return "".join(chunks)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--logical-task", required=True)
    p.add_argument("--task-id", required=True)
    p.add_argument("--dispatch-id", required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--outcome", choices=("succeeded", "failed"), required=True)
    p.add_argument("--summary", required=True)
    p.add_argument("--allow-empty", action="store_true")
    p.add_argument("--no-run-checks", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    try:
        return finish(args)
    except FleetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


def finish(args: argparse.Namespace) -> int:
    if not args.task_id.startswith("task_"):
        raise FleetError("--task-id must be the injected Orca task_... ID")
    if not args.dispatch_id.startswith("dispatch_"):
        raise FleetError("--dispatch-id must be the injected Orca dispatch_... ID")
    root = git_root()
    cfg = load_config(root)
    ctx = load_context(root)
    if not ctx:
        raise FleetError("missing task context; run scripts/gate.py init first")
    if ctx.get("logical_task_id") != args.logical_task:
        raise FleetError(f"context task {ctx.get('logical_task_id')} != {args.logical_task}")
    track = str(ctx.get("track"))
    base_sha = git_sha(root, args.base)
    if ctx.get("base_sha") != base_sha:
        raise FleetError(f"context base {ctx.get('base_sha')} != {base_sha}")

    marker = git_path(root, f"orca-worker-done-{args.dispatch_id}.json")
    if marker.exists():
        raise FleetError(f"worker_done already sent for this Dispatch; receipt: {marker}")

    branch = git_branch(root)
    head_sha = git_sha(root)
    files = changed_files(root, base_sha, "HEAD", worktree=True)
    integration: dict[str, object] | None = None
    if track == "integration":
        dependencies = ctx.get("dependency_shas") if isinstance(ctx.get("dependency_shas"), list) else None
        integration = integration_analysis(
            root,
            cfg,
            track,
            base_sha,
            "HEAD",
            ctx.get("write_paths", []),
            dependencies,
        )
        violations = list(integration["violations"])
    else:
        violations = scope_violations(cfg, track, files, ctx.get("write_paths", []))
    if violations:
        raise FleetError("scope/integration gate failed:\n- " + "\n- ".join(str(x) for x in violations))

    check_receipts = []
    if args.outcome == "succeeded":
        if not files and not args.allow_empty:
            raise FleetError("no changes after BASE_SHA; use --allow-empty only for a verified no-code task")
        if git_out(root, "status", "--porcelain"):
            raise FleetError("working tree is not clean")
        expected = f"[{args.logical_task}]"
        if track == "integration" and integration is not None:
            subjects = [commit_subject(root, commit) for commit in integration["first_parent_commits"]]
        else:
            subjects = commit_subjects(root, base_sha)
        if not subjects and not args.allow_empty and track != "integration":
            raise FleetError("no authored commits after BASE_SHA")
        invalid = [subject for subject in subjects if expected not in subject]
        if invalid:
            raise FleetError(f"authored commits missing {expected}:\n- " + "\n- ".join(invalid))
        if not args.no_run_checks:
            commands = list(cfg["tracks"][track].get("checks", [])) + list(ctx.get("checks", []))
            check_receipts = run_checks(root, [str(x) for x in commands])
        upstream_cp = run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            cwd=root,
            check=False,
        )
        if upstream_cp.returncode:
            raise FleetError("branch has no upstream; run: git push -u origin HEAD")
        upstream = upstream_cp.stdout.strip()
        upstream_sha = git_sha(root, upstream)
        if upstream_sha != head_sha:
            raise FleetError(f"HEAD is not fully pushed: HEAD={head_sha}, {upstream}={upstream_sha}")

    body = (
        f"logical_task={args.logical_task}; track={track}; branch={branch}; sha={head_sha}; "
        f"summary={args.summary}"
    )
    cp = run(
        [
            "orca", "orchestration", "send",
            "--type", "worker_done",
            "--subject", f"[{args.logical_task}] {args.outcome}",
            "--body", body,
            "--task-id", args.task_id,
            "--dispatch-id", args.dispatch_id,
            "--outcome", args.outcome,
            "--files-modified", files_argument(files),
            "--json",
        ],
        cwd=root,
    )
    receipt = parse_json(cp.stdout, "orca orchestration send")
    result = {
        "sent_at": now(),
        "logical_task_id": args.logical_task,
        "orca_task_id": args.task_id,
        "dispatch_id": args.dispatch_id,
        "outcome": args.outcome,
        "summary": args.summary,
        "track": track,
        "branch": branch,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "files": files,
        "checks": check_receipts,
        "integration": integration,
        "orca_receipt": receipt,
    }
    save_json(marker, result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"worker_done sent: {args.logical_task} {args.outcome} {branch}@{head_sha}")
        print(f"receipt: {marker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
