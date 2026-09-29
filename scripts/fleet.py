#!/usr/bin/env python3
"""Directory-owned multi-agent control plane built on Orca CLI."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping

sys.dont_write_bytecode = True
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from common import (
    FleetError,
    branch_context,
    changed_files,
    command_exists,
    commit_subject,
    commit_subjects,
    find_branch,
    find_key,
    find_prefixed,
    git_branch,
    git_root,
    git_sha,
    integration_analysis,
    load_config,
    load_json,
    now,
    parse_json,
    run,
    save_json,
    scope_violations,
    slug,
    timestamp,
    validate_plan,
    walk,
)


def cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor")
    d.add_argument("--plan", type=Path)
    d.add_argument("--json", action="store_true")

    v = sub.add_parser("validate")
    v.add_argument("plan", type=Path)
    v.add_argument("--json", action="store_true")

    c = sub.add_parser("start-coordinator")
    c.add_argument("--objective", required=True)
    c.add_argument("--agent")
    c.add_argument("--setup", choices=("run", "skip", "inherit"))
    c.add_argument("--name")
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--json", action="store_true")

    l = sub.add_parser("launch")
    l.add_argument("plan", type=Path)
    l.add_argument("--dry-run", action="store_true")
    l.add_argument("--json", action="store_true")

    i = sub.add_parser("inbox")
    i.add_argument("--state", type=Path, required=True)
    i.add_argument("--wait", action="store_true")
    i.add_argument("--types", default="worker_done,escalation,question")
    i.add_argument("--timeout-ms", type=int, default=900000)
    i.add_argument("--ack")
    i.add_argument("--peek", action="store_true")
    i.add_argument("--json", action="store_true")

    a = sub.add_parser("accept")
    a.add_argument("--state", type=Path, required=True)
    a.add_argument("--task", required=True)
    a.add_argument("--branch")
    a.add_argument("--sha")
    a.add_argument("--outcome", choices=("succeeded", "failed"), required=True)
    a.add_argument("--summary", required=True)
    a.add_argument("--retain", action="store_true")
    a.add_argument("--advance", action="store_true")
    a.add_argument("--dry-run", action="store_true")
    a.add_argument("--json", action="store_true")

    adv = sub.add_parser("advance")
    adv.add_argument("--state", type=Path, required=True)
    adv.add_argument("--dry-run", action="store_true")
    adv.add_argument("--json", action="store_true")

    s = sub.add_parser("status")
    s.add_argument("--state", type=Path, required=True)
    s.add_argument("--json", action="store_true")

    f = sub.add_parser("finalize")
    f.add_argument("--state", type=Path, required=True)
    f.add_argument("--allow-incomplete", action="store_true")
    f.add_argument("--json", action="store_true")
    return p


def orca(root: Path, args: list[str], label: str, dry_run: bool = False) -> dict[str, Any]:
    cmd = ["orca", *args]
    if "--json" not in cmd:
        cmd.append("--json")
    cp = run(cmd, cwd=root, dry_run=dry_run, echo=True)
    if dry_run:
        return {"ok": True, "dry_run": True, "command": cmd}
    value = parse_json(cp.stdout, label)
    if not isinstance(value, dict):
        raise FleetError(f"{label} must return a JSON object")
    if value.get("ok") is False:
        raise FleetError(f"{label} failed: {json.dumps(value, ensure_ascii=False)}")
    return value


def repo_selector(root: Path, cfg: Mapping[str, Any], dry_run: bool = False) -> str:
    configured = cfg.get("repo_selector", "auto")
    if isinstance(configured, str) and configured not in ("", "auto"):
        return configured
    if dry_run:
        return "id:<auto-repo-id>"
    listing = orca(root, ["repo", "list"], "orca repo list")
    target = str(root.resolve()).replace("\\", "/")
    for item in walk(listing):
        if not isinstance(item, dict):
            continue
        path = find_key(item, {"path", "repoPath", "repo_path", "root", "directory"})
        rid = find_key(item, {"id", "repoId", "repo_id"})
        if isinstance(path, str) and isinstance(rid, str):
            if str(Path(path).expanduser().resolve()).replace("\\", "/") == target:
                return "id:" + rid.removeprefix("id:")
    added = orca(root, ["repo", "add", "--path", str(root)], "orca repo add")
    rid = find_prefixed(added, "repo_") or find_key(added, {"repoId", "repo_id", "id"})
    if isinstance(rid, str) and rid:
        return "id:" + rid.removeprefix("id:")
    raise FleetError("could not resolve Orca repo ID; set repo_selector explicitly in .agents/fleet.json")


def fetch(root: Path, cfg: Mapping[str, Any], dry_run: bool = False) -> None:
    if cfg.get("fetch_before_launch", True):
        run(["git", "fetch", "--prune", "origin"], cwd=root, dry_run=dry_run, echo=True)


def resolve_sha(root: Path, ref: str, dry_run: bool = False) -> str:
    return "0" * 40 if dry_run else git_sha(root, ref)


def do_doctor(root: Path, cfg: Mapping[str, Any], args: argparse.Namespace) -> int:
    for name in ("git", "orca"):
        if not command_exists(name):
            raise FleetError(f"required command not found: {name}")
    merge_tree_help = run(["git", "merge-tree", "-h"], cwd=root, check=False)
    if "--write-tree" not in (merge_tree_help.stdout + merge_tree_help.stderr):
        raise FleetError("Git is too old for the integration gate: git merge-tree --write-tree is required")
    status = orca(root, ["status"], "orca status")
    skill = run(["orca", "skills", "get", "orchestration", "--full"], cwd=root, check=False)
    if skill.returncode:
        raise FleetError("orchestration skill missing; run: orca skills install --skill orca-cli --skill orchestration")
    plan_errors: list[str] = []
    if args.plan:
        plan_errors = validate_plan(load_json(args.plan.resolve()), cfg)
        if plan_errors:
            raise FleetError("plan errors:\n- " + "\n- ".join(plan_errors))
    result = {
        "ok": True,
        "root": str(root),
        "branch": git_branch(root),
        "tracks": sorted(cfg["tracks"]),
        "orca_status": status,
        "plan_errors": plan_errors,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("fleet doctor passed")
        print(f"repo: {root}")
        print(f"branch: {git_branch(root)}")
        print("tracks: " + ", ".join(sorted(cfg["tracks"])))
    return 0


def do_validate(cfg: Mapping[str, Any], args: argparse.Namespace) -> int:
    plan = load_json(args.plan.resolve())
    errors = validate_plan(plan, cfg)
    if args.json:
        print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    elif errors:
        print("plan invalid:\n- " + "\n- ".join(errors))
    else:
        count = sum(len(w["tasks"]) for w in plan["waves"])
        print(f"plan valid: {len(plan['waves'])} waves, {count} tasks")
    return 2 if errors else 0


def do_start_coordinator(root: Path, cfg: Mapping[str, Any], args: argparse.Namespace) -> int:
    defaults = cfg.get("coordinator", {})
    agent = args.agent or defaults.get("agent") or "codex"
    setup = args.setup or defaults.get("setup") or "run"
    prefix = defaults.get("worktree_prefix") or "fleet-control"
    name = args.name or f"{prefix}-{slug(args.objective, 24)}-{timestamp().lower()}"
    if not name.startswith("fleet-control"):
        raise FleetError("coordinator worktree name must start with fleet-control")
    selector = repo_selector(root, cfg, args.dry_run)
    fetch(root, cfg, args.dry_run)
    base_ref = str(cfg.get("base_ref", "origin/main"))
    orca(root, ["repo", "set-base-ref", "--repo", selector, "--ref", base_ref], "set base ref", args.dry_run)
    prompt = (root / ".agents" / "prompts" / "coordinator.md").read_text(encoding="utf-8")
    prompt += (
        "\n\n# Current objective\n\n" + args.objective.strip() +
        f"\n\nRepository: `{root}`\nInitial base ref: `{base_ref}`\n" +
        "Keep this same coordinator session alive while the Run is active.\n"
    )
    receipt = orca(
        root,
        [
            "worktree", "create", "--repo", selector, "--name", name,
            "--agent", str(agent), "--prompt", prompt, "--setup", str(setup),
        ],
        "create coordinator",
        args.dry_run,
    )
    result = {"ok": True, "name": name, "agent": agent, "repo_selector": selector, "receipt": receipt}
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else f"coordinator started: {name} ({agent})")
    return 0


def build_state(plan: Mapping[str, Any], run_id: str, run_dir: Path, selector: str, base_ref: str, base_sha: str, branch: str) -> dict[str, Any]:
    tasks: dict[str, Any] = {}
    waves: list[dict[str, Any]] = []
    for wave in plan["waves"]:
        ids = []
        for task in wave["tasks"]:
            tid = task["id"]
            ids.append(tid)
            tasks[tid] = {
                **task,
                "wave": wave["id"],
                "status": "planned",
                "workspace_name": f"trk-{task['track']}-{tid.lower()}",
                "orca_task_id": None,
                "dispatch_id": None,
                "branch": None,
                "base_ref": None,
                "base_sha": None,
                "head_sha": None,
                "summary": None,
                "dispatched_at": None,
                "completed_at": None,
            }
        waves.append({
            "id": wave["id"],
            "description": wave.get("description", ""),
            "depends_on": list(wave.get("depends_on", [])),
            "base": dict(wave["base"]),
            "tasks": ids,
            "status": "planned",
            "dispatched_at": None,
            "completed_at": None,
        })
    return {
        "schema_version": 1,
        "run_id": run_id,
        "objective": plan["objective"],
        "created_at": now(),
        "updated_at": now(),
        "run_dir": str(run_dir),
        "repo_selector": selector,
        "coordinator_branch": branch,
        "initial_base_ref": base_ref,
        "initial_base_sha": base_sha,
        "waves": waves,
        "tasks": tasks,
    }


def load_state(path: Path) -> tuple[Path, dict[str, Any]]:
    path = path.resolve()
    state = load_json(path)
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise FleetError(f"invalid state file: {path}")
    return path, state


def save_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = now()
    save_json(path, state)
    (path.parent / "STATUS.md").write_text(status_markdown(state), encoding="utf-8")


def wave_ready(wave: Mapping[str, Any], state: Mapping[str, Any]) -> bool:
    return wave["status"] == "planned" and all(state["tasks"][x]["status"] == "completed" for x in wave["depends_on"])


def resolve_wave_base(root: Path, state: Mapping[str, Any], wave: Mapping[str, Any], dry_run: bool) -> tuple[str, str]:
    base = wave["base"]
    if base["type"] == "ref":
        ref = str(base["value"])
        return ref, resolve_sha(root, ref, dry_run)
    task = state["tasks"][base["task"]]
    if task["status"] != "completed" or not task.get("branch") or not task.get("head_sha"):
        raise FleetError(f"base task {base['task']} is not verified complete")
    branch = clean_branch(str(task["branch"]))
    ref = f"origin/{branch}"
    run(["git", "fetch", "origin", branch], cwd=root, dry_run=dry_run, echo=True)
    if not dry_run and git_sha(root, ref) != task["head_sha"]:
        raise FleetError(f"base task remote ref drifted: {base['task']}")
    return ref, str(task["head_sha"])


def quote_arg(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_spec(root: Path, cfg: Mapping[str, Any], state: Mapping[str, Any], task: Mapping[str, Any]) -> str:
    wave = next(w for w in state["waves"] if w["id"] == task["wave"])
    deps = []
    for dep_id in wave["depends_on"]:
        dep = state["tasks"][dep_id]
        deps.append(f"- {dep_id}: branch={dep.get('branch')}; sha={dep.get('head_sha')}; track={dep.get('track')}")
    init = [
        "python scripts/gate.py init",
        f"--track {task['track']}",
        f"--task {task['id']}",
        f"--base {task['base_sha']}",
    ]
    init += [f"--write-path {quote_arg(str(x))}" for x in task.get("write_paths", [])]
    init += [f"--check {quote_arg(str(x))}" for x in task.get("checks", [])]
    if task["track"] == "integration":
        for dep_id in wave["depends_on"]:
            dep_sha = state["tasks"][dep_id].get("head_sha")
            if dep_sha:
                init.append(f"--dependency-sha {dep_sha}")
    template = "integrator.md" if task["track"] == "integration" else "worker.md"
    contract = (root / ".agents" / "prompts" / template).read_text(encoding="utf-8")
    lines = [
        f"# Logical task {task['id']}", "",
        f"Title: {task['title']}",
        f"Track: {task['track']}",
        f"Orca Run: {state['run_id']}",
        f"Frozen BASE_REF: {task['base_ref']}",
        f"Frozen BASE_SHA: {task['base_sha']}",
        f"Expected workspace/branch: {task['workspace_name']}", "",
        "## Specification", "", str(task["spec"]), "",
        "## Acceptance", "", *[f"- {x}" for x in task.get("acceptance", [])], "",
        "## Exact write paths", "", *[f"- `{x}`" for x in task.get("write_paths", [])], "",
        "## Required checks", "", *([f"- `{x}`" for x in task.get("checks", [])] or ["- Track checks only"]), "",
        "## Dependency evidence", "", *(deps or ["- None"]), "",
        "## Mandatory first commands", "", "```bash", " \\\n  ".join(init),
        "python scripts/gate.py check --preflight", "```", "",
        "The Orca worker preamble contains the actual task_... and dispatch_... IDs. Use those exact IDs in worker_finish.py.",
        "", "---", "", contract,
    ]
    return "\n".join(lines)


def dispatch_wave(root: Path, cfg: Mapping[str, Any], state: dict[str, Any], wave: dict[str, Any], state_path: Path, dry_run: bool) -> None:
    base_ref, base_sha = resolve_wave_base(root, state, wave, dry_run)
    selector = state["repo_selector"]
    orca(root, ["repo", "set-base-ref", "--repo", selector, "--ref", base_ref], f"set base for {wave['id']}", dry_run)
    evidence = Path(state["run_dir"]) / "evidence"
    defaults = cfg.get("worker_defaults", {})
    for tid in wave["tasks"]:
        task = state["tasks"][tid]
        task["base_ref"], task["base_sha"] = base_ref, base_sha
        create = orca(
            root,
            ["orchestration", "task-create", "--task-title", f"[{tid}] {task['title']}", "--spec", render_spec(root, cfg, state, task)],
            f"create task {tid}",
            dry_run,
        )
        task_id = find_prefixed(create, "task_") or (f"task_dry_{tid.lower()}" if dry_run else None)
        if not task_id:
            raise FleetError(f"task-create receipt missing task_ ID for {tid}")
        task["orca_task_id"] = task_id
        save_json(evidence / f"{tid}-task-create.json", create)
        agent = task.get("agent") or defaults.get("agent") or "codex"
        setup = task.get("setup") or defaults.get("setup") or "run"
        mode = task.get("worktree_mode") or defaults.get("worktree_mode") or "new-top-level"
        cmd = [
            "orchestration", "worker-start", "--task", task_id,
            "--worktree", str(mode), "--repo", selector, "--name", task["workspace_name"],
            "--agent", str(agent), "--setup", str(setup),
        ]
        if task.get("model"):
            cmd += ["--model", str(task["model"])]
            if task.get("effort"):
                cmd += ["--effort", str(task["effort"])]
        elif task.get("effort"):
            raise FleetError(f"task {tid}: effort requires model")
        started = orca(root, cmd, f"start worker {tid}", dry_run)
        dispatch = find_prefixed(started, "dispatch_") or (f"dispatch_dry_{tid.lower()}" if dry_run else None)
        if not dispatch:
            raise FleetError(f"worker-start receipt missing dispatch_ ID for {tid}")
        task["dispatch_id"] = dispatch
        task["branch"] = find_branch(started) or task["workspace_name"]
        task["status"] = "dispatched"
        task["dispatched_at"] = now()
        save_json(evidence / f"{tid}-worker-start.json", started)
        save_state(state_path, state)
    wave["status"] = "dispatched"
    wave["dispatched_at"] = now()
    save_state(state_path, state)


def update_waves(state: dict[str, Any]) -> None:
    for wave in state["waves"]:
        statuses = [state["tasks"][x]["status"] for x in wave["tasks"]]
        if all(x == "completed" for x in statuses):
            wave["status"] = "completed"
            wave["completed_at"] = wave.get("completed_at") or now()
        elif any(x == "failed" for x in statuses):
            wave["status"] = "failed"
        elif any(x == "dispatched" for x in statuses):
            wave["status"] = "dispatched"
        if wave["status"] == "planned" and any(state["tasks"][x]["status"] == "failed" for x in wave["depends_on"]):
            wave["status"] = "blocked"


def dispatch_ready(root: Path, cfg: Mapping[str, Any], state: dict[str, Any], state_path: Path, dry_run: bool) -> list[str]:
    update_waves(state)
    sent: list[str] = []
    for wave in state["waves"]:
        if wave_ready(wave, state):
            dispatch_wave(root, cfg, state, wave, state_path, dry_run)
            sent.append(wave["id"])
    save_state(state_path, state)
    return sent


def do_launch(root: Path, cfg: Mapping[str, Any], args: argparse.Namespace) -> int:
    plan = load_json(args.plan.resolve())
    errors = validate_plan(plan, cfg)
    if errors:
        raise FleetError("plan errors:\n- " + "\n- ".join(errors))
    branch = git_branch(root)
    if not args.dry_run and not branch.startswith("fleet-control"):
        raise FleetError(f"launch must run in fleet-control worktree, not {branch}")
    selector = repo_selector(root, cfg, args.dry_run)
    fetch(root, cfg, args.dry_run)
    base_ref = str(plan.get("base_ref") or cfg.get("base_ref") or "origin/main")
    base_sha = resolve_sha(root, base_ref, args.dry_run)
    orca(root, ["repo", "set-base-ref", "--repo", selector, "--ref", base_ref], "set initial base", args.dry_run)
    receipt = orca(root, ["orchestration", "run-create", "--objective", plan["objective"]], "run-create", args.dry_run)
    run_id = find_prefixed(receipt, "run_") or ("run_dry_run" if args.dry_run else None)
    if not run_id:
        raise FleetError("run-create receipt missing run_ ID")
    run_dir = root / ".agents" / "runs" / f"{timestamp()}-{slug(plan['objective'])}"
    run_dir.mkdir(parents=True, exist_ok=True)
    save_json(run_dir / "plan.json", plan)
    save_json(run_dir / "evidence" / "run-create.json", receipt)
    state = build_state(plan, run_id, run_dir, selector, base_ref, base_sha, branch)
    state_path = run_dir / "state.json"
    save_state(state_path, state)
    dispatched = dispatch_ready(root, cfg, state, state_path, args.dry_run)
    result = {"ok": True, "run_id": run_id, "state": str(state_path), "dispatched_waves": dispatched}
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else f"run {run_id} created; state={state_path}; dispatched={dispatched}")
    return 0


def do_inbox(root: Path, args: argparse.Namespace) -> int:
    state_path, state = load_state(args.state)
    cmd = ["orchestration", "check"]
    if args.ack:
        cmd += ["--ack", args.ack]
    if args.wait:
        cmd += ["--wait", "--types", args.types, "--timeout-ms", str(args.timeout_ms)]
    if args.peek:
        cmd.append("--peek")
    receipt = orca(root, cmd, "orchestration check")
    evidence = Path(state["run_dir"]) / "evidence" / f"inbox-{timestamp()}.json"
    save_json(evidence, receipt)
    state["last_inbox_at"] = now()
    state["last_inbox_evidence"] = str(evidence)
    save_state(state_path, state)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    if not args.json:
        print(f"saved: {evidence}")
    return 0


def clean_branch(branch: str) -> str:
    for prefix in ("refs/heads/", "refs/remotes/origin/", "origin/"):
        if branch.startswith(prefix):
            return branch[len(prefix):]
    return branch


def do_accept(root: Path, cfg: Mapping[str, Any], args: argparse.Namespace) -> int:
    state_path, state = load_state(args.state)
    if args.task not in state["tasks"]:
        raise FleetError(f"unknown task: {args.task}")
    task = state["tasks"][args.task]
    if task["status"] not in ("dispatched", "failed"):
        raise FleetError(f"task {args.task} is not awaiting completion: {task['status']}")
    branch = args.branch or task.get("branch")
    evidence: dict[str, Any] = {
        "recorded_at": now(), "logical_task_id": args.task, "outcome": args.outcome,
        "summary": args.summary, "branch": branch, "provided_sha": args.sha,
    }
    if args.outcome == "succeeded":
        if not branch or not args.sha or not re.fullmatch(r"[0-9a-fA-F]{7,40}", args.sha):
            raise FleetError("successful acceptance requires --branch and valid --sha")
        branch = clean_branch(str(branch))
        run(["git", "fetch", "origin", branch], cwd=root, dry_run=args.dry_run, echo=True)
        remote_sha = args.sha.lower() if args.dry_run else git_sha(root, f"origin/{branch}")
        if not args.dry_run and not remote_sha.startswith(args.sha.lower()):
            raise FleetError(f"provided SHA {args.sha} != remote {remote_sha}")
        files = [] if args.dry_run else changed_files(root, task["base_sha"], remote_sha)
        integration = None
        if task["track"] == "integration" and not args.dry_run:
            wave = next(w for w in state["waves"] if w["id"] == task["wave"])
            dependency_shas = [
                state["tasks"][dep_id].get("head_sha")
                for dep_id in wave["depends_on"]
                if state["tasks"][dep_id].get("head_sha")
            ]
            integration = integration_analysis(
                root, cfg, task["track"], task["base_sha"], remote_sha,
                task["write_paths"], dependency_shas,
            )
            violations = list(integration["violations"])
            subjects = [commit_subject(root, commit) for commit in integration["first_parent_commits"]]
        else:
            violations = scope_violations(cfg, task["track"], files, task["write_paths"])
            subjects = [] if args.dry_run else commit_subjects(root, task["base_sha"], remote_sha)
        if violations:
            raise FleetError("remote scope/integration violation:\n- " + "\n- ".join(str(x) for x in violations))
        expected = f"[{args.task}]"
        invalid = [x for x in subjects if expected not in x]
        if invalid:
            raise FleetError(f"remote authored commits missing {expected}:\n- " + "\n- ".join(invalid))
        task.update({
            "status": "completed", "branch": branch, "head_sha": remote_sha,
            "summary": args.summary, "completed_at": now(),
        })
        evidence.update({
            "remote_sha": remote_sha, "files": files, "commit_subjects": subjects,
            "integration": integration,
        })
    else:
        task.update({"status": "failed", "summary": args.summary, "completed_at": now()})
    dispatch = task.get("dispatch_id")
    if dispatch:
        action = "worker-retain" if args.retain else "worker-release"
        evidence["settlement"] = orca(root, ["orchestration", action, "--dispatch", dispatch], action, args.dry_run)
    evidence_path = Path(state["run_dir"]) / "evidence" / f"{args.task}-accepted.json"
    save_json(evidence_path, evidence)
    update_waves(state)
    save_state(state_path, state)
    dispatched = dispatch_ready(root, cfg, state, state_path, args.dry_run) if args.advance else []
    result = {"ok": True, "task": args.task, "status": task["status"], "evidence": str(evidence_path), "dispatched_waves": dispatched}
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else f"accepted {args.task}: {task['status']}; dispatched={dispatched}")
    return 0


def do_advance(root: Path, cfg: Mapping[str, Any], args: argparse.Namespace) -> int:
    state_path, state = load_state(args.state)
    dispatched = dispatch_ready(root, cfg, state, state_path, args.dry_run)
    result = {"ok": True, "dispatched_waves": dispatched, "state": str(state_path)}
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else (f"dispatched: {dispatched}" if dispatched else "no wave ready"))
    return 0


def status_markdown(state: Mapping[str, Any]) -> str:
    lines = [
        f"# Fleet Run Status — {state['run_id']}", "",
        f"- Objective: {state['objective']}",
        f"- Coordinator branch: `{state.get('coordinator_branch')}`",
        f"- Initial base: `{state['initial_base_ref']}` / `{state['initial_base_sha']}`",
        f"- Created: {state['created_at']}", f"- Updated: {state['updated_at']}", "",
        "## Waves", "", "| Wave | Status | Depends on | Base |", "|---|---|---|---|",
    ]
    for wave in state["waves"]:
        base = wave["base"]
        base_text = base.get("value") if base["type"] == "ref" else f"task:{base.get('task')}"
        lines.append(f"| {wave['id']} | {wave['status']} | {', '.join(wave['depends_on']) or '—'} | `{base_text}` |")
    lines += ["", "## Tasks", "", "| Task | Track | Status | Orca Task | Dispatch | Branch | SHA |", "|---|---|---|---|---|---|---|"]
    for tid, task in state["tasks"].items():
        sha = str(task.get("head_sha") or "—")
        if sha != "—": sha = sha[:12]
        lines.append(
            f"| {tid} | {task['track']} | {task['status']} | `{task.get('orca_task_id') or '—'}` | "
            f"`{task.get('dispatch_id') or '—'}` | `{task.get('branch') or '—'}` | `{sha}` |"
        )
    lines += ["", f"Evidence: `{state['run_dir']}/evidence/`", ""]
    return "\n".join(lines)


def do_status(args: argparse.Namespace) -> int:
    _, state = load_state(args.state)
    print(json.dumps(state, ensure_ascii=False, indent=2) if args.json else status_markdown(state))
    return 0


def do_finalize(args: argparse.Namespace) -> int:
    state_path, state = load_state(args.state)
    incomplete = [tid for tid, task in state["tasks"].items() if task["status"] != "completed"]
    if incomplete and not args.allow_incomplete:
        raise FleetError("incomplete tasks: " + ", ".join(incomplete))
    manifest = {
        "schema_version": 1,
        "generated_at": now(),
        "run_id": state["run_id"],
        "objective": state["objective"],
        "initial_base_ref": state["initial_base_ref"],
        "initial_base_sha": state["initial_base_sha"],
        "coordinator_branch": state.get("coordinator_branch"),
        "tasks": {
            tid: {
                "track": task["track"], "status": task["status"],
                "orca_task_id": task.get("orca_task_id"), "dispatch_id": task.get("dispatch_id"),
                "base_sha": task.get("base_sha"), "branch": task.get("branch"),
                "head_sha": task.get("head_sha"), "summary": task.get("summary"),
                "completed_at": task.get("completed_at"),
            }
            for tid, task in state["tasks"].items()
        },
        "integration_candidates": [
            {"task": tid, "branch": task.get("branch"), "sha": task.get("head_sha")}
            for tid, task in state["tasks"].items()
            if task["track"] == "integration" and task["status"] == "completed"
        ],
        "incomplete_tasks": incomplete,
        "evidence_directory": str(Path(state["run_dir"]) / "evidence"),
    }
    path = state_path.parent / "RELEASE_MANIFEST.json"
    save_json(path, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2) if args.json else f"release manifest: {path}")
    return 0


def main() -> int:
    args = cli().parse_args()
    try:
        root = git_root()
        cfg = load_config(root, args.config.resolve() if args.config else None)
        if args.cmd == "doctor": return do_doctor(root, cfg, args)
        if args.cmd == "validate": return do_validate(cfg, args)
        if args.cmd == "start-coordinator": return do_start_coordinator(root, cfg, args)
        if args.cmd == "launch": return do_launch(root, cfg, args)
        if args.cmd == "inbox": return do_inbox(root, args)
        if args.cmd == "accept": return do_accept(root, cfg, args)
        if args.cmd == "advance": return do_advance(root, cfg, args)
        if args.cmd == "status": return do_status(args)
        if args.cmd == "finalize": return do_finalize(args)
    except FleetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
