#!/usr/bin/env python3
"""GitHub 适配器。

修复了原示例代码的 4 个 bug：
  1. REST 响应用了 GraphQL 的字段名 —— primaryLanguage/stargazerCount/
     repositoryTopics 在 REST 里实际叫 language/stargazers_count/topics。
     原代码不报错，静默返回全 0（比崩掉更危险）。
  2. list(set(x)[:20]) —— set 不支持切片，TypeError。应为 list(set(x))[:20]。
  3. datetime.utcnow() - aware_datetime —— TypeError，naive 减 aware 非法。
  4. fromisoformat(x.replace("Z","")) —— 丢弃 UTC 标记，UTC+8 下 7 天窗口偏移 8 小时。
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

from .base import BaseAdapter, VerifiedTag, days_since, parse_iso, utc_now_iso
from datetime import datetime, timedelta, timezone


class GitHubAdapter(BaseAdapter):
    source_name = "github"
    BASE_URL = "https://api.github.com"

    def __init__(self, creds: Dict[str, Any], **kw):
        super().__init__(creds, **kw)
        token = self.creds.get("token")
        if token:
            # GitHub 现行推荐 Bearer；token 前缀对 PAT 仍然兼容
            self.session.headers["Authorization"] = f"Bearer {token}"
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        self.username = self.creds.get("test_username") or ""
        self.authenticated = bool(token)

    def missing_credential(self):
        if not self.username:
            return "credentials.json 的 github.test_username 为空"
        return None  # token 可选：无 token 也能读公开数据（60 次/小时）

    def rate_limit(self) -> Dict[str, Any]:
        try:
            d = self.get_json(f"{self.BASE_URL}/rate_limit")
            return d.get("resources", {}).get("core", {})
        except Exception:
            return {}

    def fetch(self) -> List[VerifiedTag]:
        u = self.username
        tags: List[VerifiedTag] = []

        # ---------- 1. 用户资料 ----------
        user = self.get_json(f"{self.BASE_URL}/users/{u}")
        tags.extend([
            VerifiedTag("github_location", "所在地区", "基础",
                        {"location": user.get("location") or ""}, self.source_name),
            VerifiedTag("github_followers", "关注者数", "社交",
                        {"count": user.get("followers", 0)}, self.source_name),
            VerifiedTag("github_repos_count", "公开仓库数", "开发",
                        {"count": user.get("public_repos", 0)}, self.source_name),
            # 修复 3：用 aware datetime 相减
            VerifiedTag("github_account_age", "GitHub 年龄", "开发",
                        {"days": days_since(user["created_at"]),
                         "createdAt": user["created_at"]}, self.source_name),
        ])

        # ---------- 2. 仓库分析 ----------
        repos = self.get_json(
            f"{self.BASE_URL}/users/{u}/repos",
            params={"sort": "updated", "type": "owner", "per_page": 100},
        )
        lang_counts: Counter = Counter()
        total_stars = 0
        all_topics: List[str] = []
        forks_count = 0

        for repo in repos:
            if repo.get("fork"):
                forks_count += 1
                continue  # fork 不代表本人技术栈，排除以免污染主语言判定
            # 修复 1：REST 的正确字段名
            lang = repo.get("language")
            if lang:
                lang_counts[lang] += 1
            total_stars += repo.get("stargazers_count", 0)
            all_topics.extend(repo.get("topics") or [])

        primary_lang = lang_counts.most_common(1)[0][0] if lang_counts else ""

        tags.extend([
            VerifiedTag("github_primary_lang", "主要编程语言", "开发",
                        {"language": primary_lang,
                         "distribution": dict(lang_counts.most_common(10))},
                        self.source_name),
            VerifiedTag("github_total_stars", "总星标数", "开发",
                        {"stars": total_stars}, self.source_name),
            # 修复 2：先 list 再切片
            VerifiedTag("github_tech_domains", "技术领域", "开发",
                        {"topics": sorted(set(all_topics))[:20]}, self.source_name),
        ])

        # ---------- 3. 近期活动 ----------
        events = self.get_json(f"{self.BASE_URL}/users/{u}/events",
                               params={"per_page": 100})
        event_types: Counter = Counter()
        # 修复 4：aware datetime 做窗口比较，无时区偏移
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        week_events = 0
        active_hours: Counter = Counter()

        for e in events:
            created = parse_iso(e["created_at"])
            if created > cutoff:
                week_events += 1
            event_types[e["type"].replace("Event", "")] += 1
            active_hours[created.hour] += 1

        tags.append(VerifiedTag(
            "github_weekly_activity", "周活跃度", "开发",
            {"events7d": week_events, "eventsSampled": len(events)},
            self.source_name))
        tags.append(VerifiedTag(
            "github_activity_type", "主要活动类型", "开发",
            {"types": dict(event_types.most_common())}, self.source_name))

        # 活跃时段（UTC 小时 → 时段），可用于跨源「作息重叠度」
        if active_hours:
            tags.append(VerifiedTag(
                "github_active_time_slot", "编码活跃时段", "开发",
                {"slot": _hour_to_slot(active_hours.most_common(1)[0][0]),
                 "histogramUtc": dict(sorted(active_hours.items()))},
                self.source_name))

        return tags


def _hour_to_slot(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 23:
        return "evening"
    return "late_night"
