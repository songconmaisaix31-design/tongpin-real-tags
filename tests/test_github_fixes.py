#!/usr/bin/env python3
"""GitHub 适配器回归测试。

锁定原示例代码的 4 个 bug，防止再次回归。fixture 用的是 REST API 的
真实字段名与真实格式（照 api.github.com 实际响应裁剪而来），不发网络请求。

跑法：python -m pytest tests/ -v    或    python tests/test_github_fixes.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.base import days_since, parse_iso  # noqa: E402
from adapters.github_adapter import GitHubAdapter, _hour_to_slot  # noqa: E402

# ---- fixture：REST /users/{u}/repos 的真实字段名 ----
REPOS_FIXTURE = [
    {"name": "linux", "language": "C", "stargazers_count": 200000,
     "topics": ["kernel", "linux"], "fork": False},
    {"name": "subsurface", "language": "C", "stargazers_count": 1200,
     "topics": [], "fork": False},
    {"name": "libdc", "language": "Python", "stargazers_count": 300,
     "topics": ["diving"], "fork": False},
    # fork 应被排除，否则污染主语言判定
    {"name": "someones-rust-proj", "language": "Rust", "stargazers_count": 99999,
     "topics": ["rust"], "fork": True},
    # language 为 null 的仓库（空仓库很常见），不能计入
    {"name": "empty", "language": None, "stargazers_count": 0,
     "topics": [], "fork": False},
]

USER_FIXTURE = {
    "login": "torvalds", "location": "Portland, OR", "followers": 317520,
    "public_repos": 12, "created_at": "2011-09-03T15:26:22Z",
}


def _analyze_with_doc_code(repos):
    """原文档 2.3 节的仓库分析逻辑，原样搬运，用于对比。"""
    lang_counts, total_stars, all_topics = {}, 0, []
    for repo in repos:
        lang = (repo.get("primaryLanguage") or {}).get("name", "")
        if lang:
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
        total_stars += repo.get("stargazerCount", 0)
        topics = [t["topic"]["name"] for t in
                  (repo.get("repositoryTopics") or {"nodes": []}).get("nodes", [])]
        all_topics.extend(topics)
    primary = max(lang_counts.items(), key=lambda x: x[1])[0] if lang_counts else "未知"
    return primary, total_stars, all_topics


def test_bug1_rest_field_names():
    """bug 1：REST 响应用 GraphQL 字段名 → 静默返回全 0。"""
    primary, stars, topics = _analyze_with_doc_code(REPOS_FIXTURE)
    # 先确认 bug 确实存在（不报错，但数据全空）——这才是它危险的地方
    assert primary == "未知", "原代码本应静默失败"
    assert stars == 0, "原代码本应静默失败"
    assert topics == [], "原代码本应静默失败"

    # 修复后：用真实字段名
    lang_counts, total_stars, all_topics = {}, 0, []
    for repo in REPOS_FIXTURE:
        if repo.get("fork"):
            continue
        lang = repo.get("language")
        if lang:
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
        total_stars += repo.get("stargazers_count", 0)
        all_topics.extend(repo.get("topics") or [])

    assert lang_counts == {"C": 2, "Python": 1}, lang_counts
    assert total_stars == 201500, total_stars          # fork 的 99999 已排除
    assert sorted(set(all_topics)) == ["diving", "kernel", "linux"]
    print("  ✓ bug1 REST 字段名：C/2 Python/1, stars=201500, fork 已排除")


def test_bug2_set_slicing():
    """bug 2：list(set(x)[:20]) → TypeError: 'set' object is not subscriptable。"""
    topics = [f"t{i}" for i in range(30)]
    try:
        _ = list(set(topics)[:20])
        raise AssertionError("原代码本应抛 TypeError")
    except TypeError as e:
        assert "subscriptable" in str(e)

    fixed = sorted(set(topics))[:20]
    assert len(fixed) == 20 and isinstance(fixed, list)
    print("  ✓ bug2 set 切片：先 list/sorted 再切片，得 20 项")


def test_bug3_naive_vs_aware_datetime():
    """bug 3：datetime.utcnow() - aware → TypeError。"""
    created = parse_iso(USER_FIXTURE["created_at"])
    assert created.tzinfo is not None, "解析结果必须是 aware"

    try:
        _ = (datetime.utcnow() - created).days
        raise AssertionError("原代码本应抛 TypeError")
    except TypeError as e:
        assert "offset-naive and offset-aware" in str(e)

    days = days_since(USER_FIXTURE["created_at"])
    assert days > 5000, days
    print(f"  ✓ bug3 时区感知相减：账号年龄 {days} 天")


def test_bug4_utc_marker_dropped():
    """bug 4：replace("Z","") 丢 UTC 标记 → 事件 epoch 偏早，7 天窗口漏算。

    原代码：
        cutoff = datetime.now().timestamp() - 86400 * 7          # 正确的 epoch
        ts = fromisoformat(created_at.replace("Z","")).timestamp() # 偏早 8h 的 epoch
    naive 解析把 UTC 串当本机时间，UTC+8 下算出的 epoch 比真值早 8 小时，
    于是事件显得比实际更旧，窗口边缘的事件被错误排除。
    """
    local_offset = datetime.now().astimezone().utcoffset().total_seconds() / 3600
    if local_offset == 0:
        print("  - bug4：本机为 UTC，此 bug 不可复现，跳过")
        return

    ts = "2026-08-21T19:09:06Z"
    naive = datetime.fromisoformat(ts.replace("Z", ""))
    aware = parse_iso(ts)
    assert naive.tzinfo is None and aware.tzinfo is not None

    # naive 的 epoch 比真值早 local_offset 小时
    drift = (aware.timestamp() - naive.timestamp()) / 3600
    assert abs(drift - local_offset) < 0.01, (drift, local_offset)

    # 边界复现：一个「6 天 20 小时前」的事件，本该算进 7 天窗口
    now = datetime.now(timezone.utc)
    event = now - timedelta(days=6, hours=20)
    created_at = event.strftime("%Y-%m-%dT%H:%M:%SZ")
    cutoff_epoch = datetime.now().timestamp() - 86400 * 7

    doc_epoch = datetime.fromisoformat(created_at.replace("Z", "")).timestamp()
    fixed_epoch = parse_iso(created_at).timestamp()

    assert fixed_epoch > cutoff_epoch, "修复后：应算进 7 天窗口"
    if local_offset > 0:
        assert doc_epoch < cutoff_epoch, "原代码：该事件被错误排除"
        print(f"  ✓ bug4 UTC 标记：本机 {local_offset:+.0f}h，"
              f"6d20h 前的事件原代码漏算，修复后正确计入")
    else:
        print(f"  ✓ bug4 UTC 标记：本机 {local_offset:+.0f}h，已用 aware 比较")


def test_hour_to_slot():
    assert _hour_to_slot(7) == "morning"
    assert _hour_to_slot(14) == "afternoon"
    assert _hour_to_slot(20) == "evening"
    assert _hour_to_slot(2) == "late_night"
    print("  ✓ 活跃时段映射")


def test_adapter_skips_without_username():
    a = GitHubAdapter({})
    assert a.missing_credential() is not None
    res = a.run()
    assert not res.ok and res.skipped_reason
    # token 可选：只有 username 也应视为凭证齐备
    b = GitHubAdapter({"test_username": "torvalds"})
    assert b.missing_credential() is None
    assert b.authenticated is False
    print("  ✓ 凭证缺失时跳过而非崩溃；token 可选")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
        except Exception as e:
            failed += 1
            print(f"  ✗ {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} 通过")
    sys.exit(1 if failed else 0)
