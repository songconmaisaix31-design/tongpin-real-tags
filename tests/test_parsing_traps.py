#!/usr/bin/env python3
"""LeetCode / Duolingo 解析陷阱的回归测试。

这两个源无需鉴权就能用，但各有一个容易踩的坑，都是实测中发现的。
fixture 照真实响应裁剪，不发网络请求。

跑法：python tests/test_parsing_traps.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.duolingo_adapter import DuolingoAdapter  # noqa: E402
from adapters.leetcode_adapter import LeetCodeAdapter, _to_num  # noqa: E402


def test_leetcode_com_excludes_all_summary():
    """.com 的 acSubmissionNum 含 All 汇总项，计入总数会翻倍。

    实测 votrubac：All=3824，而 Easy+Medium+Hard=932+2004+888=3824。
    若把 All 也累加，总数会变成 7648。
    """
    a = LeetCodeAdapter({"site": "com", "username": "x"})
    # 真实响应形状
    stats = {
        "All": {"difficulty": "All", "count": 3824, "submissions": 28972},
        "Easy": {"difficulty": "Easy", "count": 932, "submissions": 2934},
        "Medium": {"difficulty": "Medium", "count": 2004, "submissions": 14180},
        "Hard": {"difficulty": "Hard", "count": 888, "submissions": 11858},
    }
    tags = a._solve_tags(
        easy=stats["Easy"]["count"],
        medium=stats["Medium"]["count"],
        hard=stats["Hard"]["count"],
        submissions=stats["All"]["submissions"],
    )
    solved = next(t for t in tags if t.tag_id == "leetcode_solved")
    assert solved.value["total"] == 3824, solved.value
    assert solved.value["total"] == stats["All"]["count"], "应与 All 汇总一致"
    naive_sum = sum(v["count"] for v in stats.values())
    assert naive_sum == 7648, "把 All 计入会翻倍"
    print("  ✓ .com 排除 All 汇总项：total=3824（含 All 会错成 7648）")


def test_leetcode_cn_uppercase_difficulty():
    """.cn 的难度枚举是大写 EASY/MEDIUM/HARD，用 .com 的大小写会全部取不到。"""
    cn_response = [
        {"difficulty": "EASY", "count": 25},
        {"difficulty": "MEDIUM", "count": 26},
        {"difficulty": "HARD", "count": 14},
    ]
    # 适配器的取值方式：统一 upper() 后再查
    by = {(x["difficulty"] or "").upper(): x["count"] for x in cn_response}
    assert (by.get("EASY"), by.get("MEDIUM"), by.get("HARD")) == (25, 26, 14)

    # 若照 .com 的大小写去取，全都是 0
    wrong = {x["difficulty"]: x["count"] for x in cn_response}
    assert wrong.get("Easy") is None and wrong.get("Hard") is None
    print("  ✓ .cn 大写难度枚举：EASY/MEDIUM/HARD = 25/26/14")


def test_leetcode_cn_ranking_is_object():
    """.cn 的 profile.ranking 是对象且 currentRating 是字符串；.com 是标量 Int。"""
    assert _to_num("910") == 910.0
    assert _to_num(71) == 71
    assert _to_num(None) is None
    assert _to_num("n/a") == "n/a"     # 非数字原样返回，不抛错
    print("  ✓ ranking 类型差异：'910'→910.0，标量与 None 原样")


def test_leetcode_rejects_bad_site():
    a = LeetCodeAdapter({"site": "jp", "username": "x"})
    assert a.missing_credential() is not None
    res = a.run()
    assert not res.ok and res.skipped_reason
    print("  ✓ site 非法时跳过而非发错误请求")


def test_duolingo_null_current_streak():
    """接口文档说打卡判定用 streakData.currentStreak.endDate，

    但实测连胜为 0 时 currentStreak 是 null（官方账号 duo 就是这样），
    直接取 .endDate 会 AttributeError。必须判空。
    """
    a = DuolingoAdapter({"username": "duo"})

    # 真实响应：streak=0 时 currentStreak 为 null
    null_case = {"streak": 0, "streakData": {"currentStreak": None}}
    st = a.check_today_status(null_case)
    assert st == {"checkedInToday": False, "currentStreak": 0,
                  "lastCheckinDate": ""}, st

    # 照文档字面写法会崩
    try:
        _ = null_case["streakData"]["currentStreak"]["endDate"]
        raise AssertionError("文档写法本应抛错")
    except TypeError:
        pass
    print("  ✓ currentStreak 为 null 时不崩，返回未打卡")


def test_duolingo_checked_in_today():
    """连胜存在且 endDate 是今天 → 判定已打卡。"""
    a = DuolingoAdapter({"username": "x"})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    st = a.check_today_status(
        {"streak": 365, "streakData": {"currentStreak": {"endDate": today}}})
    assert st["checkedInToday"] is True and st["currentStreak"] == 365

    st = a.check_today_status(
        {"streak": 12, "streakData": {"currentStreak": {"endDate": "2020-01-01"}}})
    assert st["checkedInToday"] is False and st["lastCheckinDate"] == "2020-01-01"
    print("  ✓ endDate==今日→已打卡；历史日期→未打卡")


def test_duolingo_missing_streak_data():
    """streakData 整个缺失也不能崩（字段并非始终存在）。"""
    a = DuolingoAdapter({"username": "x"})
    st = a.check_today_status({"streak": 5})
    assert st["currentStreak"] == 5 and st["checkedInToday"] is False
    st = a.check_today_status({})
    assert st["currentStreak"] == 0
    print("  ✓ streakData 缺失时安全降级")


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
