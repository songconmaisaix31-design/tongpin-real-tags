#!/usr/bin/env python3
"""Standard-library helpers for the Orca directory-fleet kit."""
from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


class FleetError(RuntimeError):
    pass


def run(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    dry_run: bool = False,
    echo: bool = False,
) -> subprocess.CompletedProcess[str]:
    cmd = [str(x) for x in args]
    if echo or dry_run:
        print("+ " + " ".join(_display(x) for x in cmd))
    if dry_run:
        return subprocess.CompletedProcess(cmd, 0, "{}", "")
    cp = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and cp.returncode:
        detail = cp.stderr.strip() or cp.stdout.strip() or "no output"
        raise FleetError(f"command failed ({cp.returncode}): {' '.join(cmd)}\n{detail}")
    return cp


def _display(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:@+-]+", value):
        return value
    return json.dumps(value, ensure_ascii=False)


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def git_root(cwd: Path | None = None) -> Path:
    return Path(run(["git", "rev-parse", "--show-toplevel"], cwd=cwd).stdout.strip()).resolve()


def git_out(root: Path, *args: str, check: bool = True) -> str:
    return run(["git", *args], cwd=root, check=check).stdout.strip()


def git_branch(root: Path) -> str:
    return git_out(root, "branch", "--show-current")


def git_sha(root: Path, ref: str = "HEAD") -> str:
    return git_out(root, "rev-parse", ref)


def git_path(root: Path, name: str) -> Path:
    raw = Path(git_out(root, "rev-parse", "--git-path", name))
    return (raw if raw.is_absolute() else root / raw).resolve()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FleetError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise FleetError(f"invalid JSON {path}:{exc.lineno}:{exc.colno}: {exc.msg}") from exc


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        tmp.write(text)
        tmp_name = tmp.name
    os.replace(tmp_name, path)


def parse_json(text: str, label: str) -> Any:
    text = text.strip()
    if not text:
        raise FleetError(f"{label} returned empty output")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for line in reversed([line.strip() for line in text.splitlines() if line.strip()]):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
    raise FleetError(f"{label} did not return JSON; tail:\n{text[-1200:]}")


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def slug(value: str, limit: int = 42) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "task"
    return value[:limit].rstrip("-")


def walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def find_prefixed(value: Any, prefix: str) -> str | None:
    for item in walk(value):
        if isinstance(item, str) and item.startswith(prefix):
            return item
    return None


def find_key(value: Any, names: set[str]) -> Any | None:
    wanted = {x.lower() for x in names}
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in wanted:
                return child
        for child in value.values():
            hit = find_key(child, wanted)
            if hit is not None:
                return hit
    elif isinstance(value, list):
        for child in value:
            hit = find_key(child, wanted)
            if hit is not None:
                return hit
    return None


def find_branch(value: Any) -> str | None:
    found = find_key(value, {"branch", "branchName", "branch_name", "gitBranch", "ref"})
    if not isinstance(found, str) or not found:
        return None
    for prefix in ("refs/heads/", "refs/remotes/origin/", "origin/"):
        if found.startswith(prefix):
            return found[len(prefix):]
    return found


def path_matches(path: str, pattern: str) -> bool:
    path = path.replace("\\", "/").lstrip("./")
    pattern = pattern.replace("\\", "/").lstrip("./")
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return fnmatch.fnmatchcase(path, pattern)


def path_allowed(path: str, patterns: Iterable[str]) -> bool:
    return any(path_matches(path, pattern) for pattern in patterns)


def simple_prefix(pattern: str) -> str | None:
    pattern = pattern.replace("\\", "/").lstrip("./")
    if pattern.endswith("/**"):
        return pattern[:-3].rstrip("/")
    if not any(ch in pattern for ch in "*?["):
        return pattern.rstrip("/")
    return None


def pattern_within(child: str, parent: str) -> bool:
    if child == parent:
        return True
    c, p = simple_prefix(child), simple_prefix(parent)
    return bool(c is not None and p is not None and (c == p or c.startswith(p + "/")))


def patterns_overlap(a: str, b: str) -> bool:
    pa, pb = simple_prefix(a), simple_prefix(b)
    if pa is None or pb is None:
        return a == b
    return pa == pb or pa.startswith(pb + "/") or pb.startswith(pa + "/")


def load_config(root: Path, path: Path | None = None) -> dict[str, Any]:
    cfg = load_json(path or root / ".agents" / "fleet.json")
    if not isinstance(cfg, dict) or cfg.get("schema_version") != 1:
        raise FleetError(".agents/fleet.json must be an object with schema_version=1")
    tracks = cfg.get("tracks")
    if not isinstance(tracks, dict) or not tracks:
        raise FleetError("fleet config must define tracks")
    owners: list[tuple[str, str]] = []
    for track, body in tracks.items():
        if not re.fullmatch(r"[a-z0-9_]+", track):
            raise FleetError(f"invalid track id: {track}")
        allow = body.get("allow") if isinstance(body, dict) else None
        if not isinstance(allow, list) or not allow:
            raise FleetError(f"track {track} needs a non-empty allow list")
        owners.extend((track, str(p)) for p in allow)
    conflicts: list[str] = []
    for i, (ta, pa) in enumerate(owners):
        for tb, pb in owners[i + 1:]:
            if ta != tb and patterns_overlap(pa, pb):
                conflicts.append(f"{ta}:{pa} <-> {tb}:{pb}")
    if conflicts:
        raise FleetError("ownership overlap:\n- " + "\n- ".join(conflicts))
    return cfg


def branch_context(cfg: Mapping[str, Any], branch: str) -> tuple[str | None, str | None]:
    rules = cfg.get("branch_rules", {})
    if re.search(str(rules.get("control_pattern", r"^fleet-control(?:-|$)")), branch):
        return "control", None
    match = re.search(
        str(rules.get("track_pattern", r"^trk-(?P<track>[a-z0-9_]+)-(?P<task>[a-z0-9-]+)$")),
        branch,
    )
    return (match.groupdict().get("track"), match.groupdict().get("task")) if match else (None, None)


def context_path(root: Path) -> Path:
    return git_path(root, "orca-agent-context.json")


def load_context(root: Path) -> dict[str, Any] | None:
    path = context_path(root)
    return load_json(path) if path.exists() else None


def changed_files(root: Path, base: str, head: str = "HEAD", worktree: bool = False) -> list[str]:
    files = set(git_out(root, "diff", "--name-only", f"{base}...{head}", check=False).splitlines())
    if worktree and head == "HEAD":
        files.update(git_out(root, "diff", "--name-only", check=False).splitlines())
        files.update(git_out(root, "diff", "--name-only", "--cached", check=False).splitlines())
        files.update(git_out(root, "ls-files", "--others", "--exclude-standard", check=False).splitlines())
    return sorted(x.replace("\\", "/") for x in files if x.strip())


def scope_violations(
    cfg: Mapping[str, Any], track: str, files: Iterable[str], task_allow: Iterable[str] | None = None
) -> list[str]:
    if track not in cfg["tracks"]:
        raise FleetError(f"unknown track: {track}")
    track_allow = list(cfg["tracks"][track].get("allow", []))
    forbidden = list(cfg.get("global_forbidden", [])) + list(cfg["tracks"][track].get("forbidden", []))
    task_allow = list(task_allow or [])
    out: list[str] = []
    for path in files:
        if path_allowed(path, forbidden):
            out.append(f"FORBIDDEN {path}")
        elif not path_allowed(path, track_allow):
            out.append(f"OUTSIDE_TRACK {path}")
        elif task_allow and not path_allowed(path, task_allow):
            out.append(f"OUTSIDE_TASK {path}")
    return out


def commit_subjects(root: Path, base: str, head: str = "HEAD") -> list[str]:
    return [x for x in git_out(root, "log", "--format=%s", f"{base}..{head}", check=False).splitlines() if x]


def run_checks(root: Path, commands: Iterable[str]) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for command in commands:
        if not command.strip():
            continue
        cp = subprocess.run(
            command,
            cwd=root,
            shell=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        receipt = {
            "command": command,
            "returncode": cp.returncode,
            "stdout": cp.stdout[-4000:],
            "stderr": cp.stderr[-4000:],
        }
        receipts.append(receipt)
        if cp.returncode:
            raise FleetError(f"check failed: {command}\n{cp.stderr.strip() or cp.stdout.strip()}")
    return receipts


def validate_plan(plan: Mapping[str, Any], cfg: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if plan.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not isinstance(plan.get("objective"), str) or not plan["objective"].strip():
        errors.append("objective must be non-empty")
    waves = plan.get("waves")
    if not isinstance(waves, list) or not waves:
        return errors + ["waves must be a non-empty list"]
    prior: set[str] = set()
    all_ids: set[str] = set()
    wave_ids: set[str] = set()
    for wi, wave in enumerate(waves):
        if not isinstance(wave, dict):
            errors.append(f"waves[{wi}] must be an object")
            continue
        wid = wave.get("id")
        if not isinstance(wid, str) or not wid:
            errors.append(f"waves[{wi}].id must be non-empty")
            wid = f"wave-{wi}"
        elif wid in wave_ids:
            errors.append(f"duplicate wave id: {wid}")
        wave_ids.add(str(wid))
        deps = wave.get("depends_on", [])
        if not isinstance(deps, list) or not all(isinstance(x, str) for x in deps):
            errors.append(f"wave {wid}: depends_on must be a string list")
            deps = []
        for dep in deps:
            if dep not in prior:
                errors.append(f"wave {wid}: dependency {dep} must be from an earlier wave")
        base = wave.get("base", {})
        if base.get("type") == "task":
            base_task = base.get("task")
            if base_task not in prior:
                errors.append(f"wave {wid}: base task must be earlier")
            if base_task not in deps:
                errors.append(f"wave {wid}: base task {base_task} must also be in depends_on")
        elif base.get("type") == "ref":
            if not isinstance(base.get("value"), str):
                errors.append(f"wave {wid}: ref base needs value")
        else:
            errors.append(f"wave {wid}: base.type must be ref or task")
        tasks = wave.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            errors.append(f"wave {wid}: tasks must be non-empty")
            continue
        seen_tracks: set[str] = set()
        paths: list[tuple[str, str]] = []
        current: set[str] = set()
        for ti, task in enumerate(tasks):
            if not isinstance(task, dict):
                errors.append(f"wave {wid} task[{ti}] must be an object")
                continue
            tid = task.get("id")
            if not isinstance(tid, str) or not re.fullmatch(r"[A-Z][A-Z0-9_-]*-\d+", tid):
                errors.append(f"wave {wid} task[{ti}] id must look like WEB-001")
                continue
            if tid in all_ids:
                errors.append(f"duplicate task id: {tid}")
            all_ids.add(tid)
            current.add(tid)
            track = task.get("track")
            if track not in cfg["tracks"]:
                errors.append(f"task {tid}: unknown track {track}")
                continue
            if track in seen_tracks:
                errors.append(f"wave {wid}: track {track} appears twice")
            seen_tracks.add(track)
            write_paths = task.get("write_paths")
            if not isinstance(write_paths, list) or not write_paths:
                errors.append(f"task {tid}: write_paths must be non-empty")
                write_paths = []
            for pattern in write_paths:
                if not any(pattern_within(pattern, allowed) for allowed in cfg["tracks"][track]["allow"]):
                    errors.append(f"task {tid}: {pattern} is outside track {track}")
                for other_id, other_pattern in paths:
                    if patterns_overlap(pattern, other_pattern):
                        errors.append(f"wave {wid}: overlap {tid}:{pattern} <-> {other_id}:{other_pattern}")
                paths.append((tid, pattern))
            for field in ("title", "spec"):
                if not isinstance(task.get(field), str) or not task[field].strip():
                    errors.append(f"task {tid}: {field} must be non-empty")
        prior.update(current)
    return errors


def worktree_files(root: Path) -> list[str]:
    """Return only staged, unstaged and untracked files, excluding committed history."""
    files: set[str] = set()
    files.update(git_out(root, "diff", "--name-only", check=False).splitlines())
    files.update(git_out(root, "diff", "--name-only", "--cached", check=False).splitlines())
    files.update(git_out(root, "ls-files", "--others", "--exclude-standard", check=False).splitlines())
    return sorted(x.replace("\\", "/") for x in files if x.strip())


def is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    return run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=root,
        check=False,
    ).returncode == 0


def commit_parents(root: Path, commit: str) -> list[str]:
    fields = git_out(root, "rev-list", "--parents", "-n", "1", commit).split()
    if not fields or fields[0] != git_sha(root, commit):
        raise FleetError(f"cannot inspect commit parents: {commit}")
    return fields[1:]


def commit_files(root: Path, commit: str) -> list[str]:
    output = git_out(root, "diff-tree", "--no-commit-id", "--name-only", "-r", commit, check=False)
    return sorted(x.replace("\\", "/") for x in output.splitlines() if x.strip())


def commit_subject(root: Path, commit: str) -> str:
    return git_out(root, "show", "-s", "--format=%s", commit)


def integration_analysis(
    root: Path,
    cfg: Mapping[str, Any],
    track: str,
    base: str,
    head: str = "HEAD",
    task_allow: Iterable[str] | None = None,
    dependency_shas: Iterable[str] | None = None,
    require_all_dependencies: bool = True,
) -> dict[str, Any]:
    """Validate an integration branch without treating merged worker files as authored.

    The first-parent chain is the integration track's own history. Normal commits
    on that chain may touch only integration-owned paths. Every merge must be a
    two-parent, clean, automatic no-ff merge. When dependency SHAs are supplied,
    they are also checked against the exact second parents of those merge commits.
    """
    base_sha = git_sha(root, base)
    head_sha = git_sha(root, head)
    first_parent_output = git_out(
        root,
        "rev-list",
        "--first-parent",
        "--reverse",
        f"{base_sha}..{head_sha}",
        check=False,
    )
    first_parent_commits = [x for x in first_parent_output.splitlines() if x.strip()]

    provided = [git_sha(root, str(dep)) for dep in (dependency_shas or [])]
    # A dependency that is already contained in BASE_SHA is the foundation
    # baseline and does not need another merge commit.
    required_dependencies = [dep for dep in provided if not is_ancestor(root, dep, base_sha)]

    violations: list[str] = []
    authored_commits: list[str] = []
    merge_commits: list[dict[str, Any]] = []
    merged_heads: list[str] = []

    for commit in first_parent_commits:
        parents = commit_parents(root, commit)
        if len(parents) == 1:
            authored_commits.append(commit)
            files = commit_files(root, commit)
            for violation in scope_violations(cfg, track, files, task_allow):
                violations.append(f"INTEGRATION_COMMIT {commit[:12]} {violation}")
            continue

        if len(parents) != 2:
            violations.append(
                f"INTEGRATION_MERGE {commit[:12]} must have exactly two parents; found {len(parents)}"
            )
            continue

        first_parent, merged_head = parents
        merged_heads.append(merged_head)
        merge_info: dict[str, Any] = {
            "commit": commit,
            "first_parent": first_parent,
            "merged_head": merged_head,
            "subject": commit_subject(root, commit),
        }

        if provided and merged_head not in required_dependencies:
            violations.append(
                f"UNAPPROVED_MERGE {commit[:12]} second parent {merged_head[:12]} is not an accepted dependency"
            )

        # Recompute Git's clean automatic merge. A conflict or a manually edited
        # merge tree fails: integration changes must be separate owned-path commits.
        merge_tree = run(
            ["git", "merge-tree", "--write-tree", first_parent, merged_head],
            cwd=root,
            check=False,
        )
        if merge_tree.returncode != 0:
            detail = merge_tree.stderr.strip() or merge_tree.stdout.strip() or "merge conflict"
            violations.append(f"CONFLICTING_MERGE {commit[:12]}: {detail[-500:]}")
            merge_info["automatic"] = False
        else:
            expected_tree = next(
                (line.strip() for line in merge_tree.stdout.splitlines() if re.fullmatch(r"[0-9a-f]{40}", line.strip())),
                None,
            )
            actual_tree = git_out(root, "show", "-s", "--format=%T", commit)
            merge_info.update({"automatic": expected_tree == actual_tree, "expected_tree": expected_tree, "actual_tree": actual_tree})
            if expected_tree != actual_tree:
                violations.append(
                    f"MANUALLY_EDITED_MERGE {commit[:12]} tree {actual_tree[:12]} != automatic {str(expected_tree)[:12]}"
                )
        merge_commits.append(merge_info)

    if provided and require_all_dependencies:
        for dep in required_dependencies:
            if not is_ancestor(root, dep, head_sha):
                violations.append(f"MISSING_DEPENDENCY {dep[:12]} is not contained in integration HEAD")
            if dep not in merged_heads:
                violations.append(f"NO_NO_FF_MERGE {dep[:12]} is not an exact second parent of an integration merge")

    return {
        "base_sha": base_sha,
        "head_sha": head_sha,
        "first_parent_commits": first_parent_commits,
        "authored_commits": authored_commits,
        "merge_commits": merge_commits,
        "merged_heads": merged_heads,
        "dependency_shas": provided or merged_heads,
        "violations": violations,
    }
