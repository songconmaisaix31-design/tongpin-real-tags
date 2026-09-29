#!/usr/bin/env python3
"""Duolingo 适配器。

接口文档定义了 IDuolingoAdapter 但没给实现，本文件补上。
实测 https://www.duolingo.com/2017-06-30/users?username=X 无需鉴权返回 200。
（旧路径 /users/{name} 已废弃，返回 401。）

关于 checkTodayStatus：接口文档说判定依据是
  streakData.currentStreak.endDate == 今日
实测 currentStreak 在连胜为 0 时是 null（如官方账号 duo），
所以必须判空，不能直接取 .endDate。
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import BaseAdapter, VerifiedTag


class DuolingoAdapter(BaseAdapter):
    source_name = "duolingo"
    BASE_URL = "https://www.duolingo.com/2017-06-30"

    def __init__(self, creds: Dict[str, Any], **kw):
        super().__init__(creds, **kw)
        self.username = self.creds.get("username") or ""

    def missing_credential(self):
        if not self.username:
            return "credentials.json 的 duolingo.username 为空"
        return None

    def fetch_user(self) -> Dict[str, Any]:
        d = self.get_json(f"{self.BASE_URL}/users",
                          params={"username": self.username})
        users = d.get("users") or []
        if not users:
            raise RuntimeError(f"用户不存在或资料非公开: {self.username}")
        return users[0]

    def check_today_status(self, u: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """对应 IDuolingoAdapter.checkTodayStatus。

        u 为 None 时才联网拉取；传入 {} 视为「已给定数据但内容为空」，
        不应触发请求（用 `u or fetch()` 会把 {} 当假值而误发请求）。
        """
        u = self.fetch_user() if u is None else u
        streak = u.get("streak", 0) or 0
        sd = u.get("streakData") or {}
        cur = sd.get("currentStreak")  # 连胜为 0 时是 null，必须判空

        last_date = ""
        checked_in_today = False
        if isinstance(cur, dict):
            last_date = cur.get("endDate") or ""
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            checked_in_today = last_date == today

        return {
            "checkedInToday": checked_in_today,
            "currentStreak": streak,
            "lastCheckinDate": last_date,
        }

    def fetch(self) -> List[VerifiedTag]:
        u = self.fetch_user()
        tags: List[VerifiedTag] = []

        # ---------- 语言学习 ----------
        courses = u.get("courses") or []
        langs = [c.get("learningLanguage") for c in courses if c.get("learningLanguage")]
        course_detail = [
            {"language": c.get("learningLanguage"),
             "title": c.get("title"),
             "xp": c.get("xp", 0)}
            for c in sorted(courses, key=lambda c: c.get("xp", 0), reverse=True)
        ]

        tags.append(VerifiedTag(
            "lang_learning", "正在学习的语种", "学习",
            {"languages": langs,
             "primary": u.get("learningLanguage") or "",
             "fromLanguage": u.get("fromLanguage") or "",
             "courses": course_detail[:10]},
            self.source_name))

        # ---------- 连胜与打卡 ----------
        status = self.check_today_status(u)
        tags.append(VerifiedTag(
            "streak_days", "连续学习天数", "学习",
            {"days": status["currentStreak"],
             "checkedInToday": status["checkedInToday"],
             "lastCheckinDate": status["lastCheckinDate"]},
            self.source_name))

        # ---------- 经验与等级 ----------
        total_xp = u.get("totalXp", 0) or 0
        tags.append(VerifiedTag(
            "level_xp", "累计经验值", "学习",
            {"totalXp": total_xp,
             "hasPlus": bool(u.get("hasPlus"))},
            self.source_name))

        # ---------- 学习坚持度（推导，对应 learning_consistency）----------
        streak = status["currentStreak"]
        if streak >= 180:
            level = "硬核"
        elif streak >= 90:
            level = "稳定"
        elif streak >= 30:
            level = "轻度"
        else:
            level = "起步"
        tags.append(VerifiedTag(
            "learning_consistency", "学习坚持度", "学习",
            {"level": level, "basisStreakDays": streak},
            self.source_name))

        # ---------- 账号年龄 ----------
        if u.get("creationDate"):
            created = datetime.fromtimestamp(u["creationDate"], tz=timezone.utc)
            tags.append(VerifiedTag(
                "duolingo_account_age", "Duolingo 账号年龄", "学习",
                {"days": (datetime.now(timezone.utc) - created).days,
                 "createdAt": created.isoformat()},
                self.source_name))

        return tags
