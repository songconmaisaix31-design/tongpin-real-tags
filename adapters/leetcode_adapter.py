#!/usr/bin/env python3
"""LeetCode 适配器（力扣）。

接口文档把 LEETCODE 列进了 DataSourceType 枚举但没有任何调研或实现，本文件补上。
实测 leetcode.cn 与 leetcode.com 的 GraphQL 都无需鉴权即可读公开资料。

重要：两站 schema 并不相同，不能共用一套 query。实测差异：
  - .com  用 matchedUser(username:) ，profile.ranking 是标量 Int
  - .cn   用 userProfilePublicProfile(userSlug:) ，profile.ranking 是对象
          （需子选择 currentRating / currentGlobalRanking，没有 totalRating 字段）
  - .cn   题目进度走 userProfileUserQuestionProgress，难度枚举是大写
          EASY/MEDIUM/HARD；.com 走 submitStats.acSubmissionNum，
          难度是 All/Easy/Medium/Hard（含 All 汇总项，统计时要排除）
  - .cn   关闭了 GraphQL introspection
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import BaseAdapter, VerifiedTag

_COM_QUERY = """
query($u: String!) {
  matchedUser(username: $u) {
    username
    githubUrl
    profile { realName aboutMe countryName ranking reputation skillTags }
    submitStats { acSubmissionNum { difficulty count submissions } }
    userCalendar { streak totalActiveDays activeYears }
  }
}
"""

_CN_PROFILE_QUERY = """
query($s: String!) {
  userProfilePublicProfile(userSlug: $s) {
    username
    profile {
      userSlug realName aboutMe countryName skillTags
      ranking { currentRating currentGlobalRanking }
    }
  }
}
"""

_CN_PROGRESS_QUERY = """
query($s: String!) {
  userProfileUserQuestionProgress(userSlug: $s) {
    numAcceptedQuestions { difficulty count }
  }
}
"""


class LeetCodeAdapter(BaseAdapter):
    source_name = "leetcode"

    def __init__(self, creds: Dict[str, Any], **kw):
        super().__init__(creds, **kw)
        self.site = (self.creds.get("site") or "cn").lower()
        self.username = self.creds.get("username") or ""
        self.host = "https://leetcode.cn" if self.site == "cn" else "https://leetcode.com"
        self.session.headers.update({
            "Content-Type": "application/json",
            "Referer": f"{self.host}/u/{self.username}/",
            "Origin": self.host,
        })
        cookie = self.creds.get("cookie")
        if cookie:
            self.session.headers["Cookie"] = cookie

    def missing_credential(self):
        if not self.username:
            return "credentials.json 的 leetcode.username 为空"
        if self.site not in ("cn", "com"):
            return f"leetcode.site 只能是 cn 或 com，当前为 {self.site!r}"
        return None

    def _gql(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        d = self.post_json(f"{self.host}/graphql",
                           json={"query": query, "variables": variables})
        if d.get("errors"):
            raise RuntimeError(f"GraphQL 错误: {d['errors'][:1]}")
        return d.get("data") or {}

    def fetch(self) -> List[VerifiedTag]:
        return self._fetch_cn() if self.site == "cn" else self._fetch_com()

    # ---------- leetcode.cn ----------

    def _fetch_cn(self) -> List[VerifiedTag]:
        tags: List[VerifiedTag] = []
        data = self._gql(_CN_PROFILE_QUERY, {"s": self.username})
        node = data.get("userProfilePublicProfile")
        if not node:
            raise RuntimeError(f"用户不存在或资料非公开: {self.username}")
        prof = node.get("profile") or {}
        ranking = prof.get("ranking") or {}

        tags.append(VerifiedTag(
            "leetcode_profile", "力扣资料", "开发",
            {"username": node.get("username") or self.username,
             "country": prof.get("countryName") or "",
             "globalRanking": ranking.get("currentGlobalRanking"),
             "contestRating": _to_num(ranking.get("currentRating"))},
            self.source_name))

        if prof.get("skillTags"):
            tags.append(VerifiedTag(
                "leetcode_skill_tags", "技能标签", "开发",
                {"tags": prof["skillTags"][:20]}, self.source_name))

        # 题目进度：.cn 难度枚举是大写
        prog = self._gql(_CN_PROGRESS_QUERY, {"s": self.username})
        node = prog.get("userProfileUserQuestionProgress") or {}
        by_diff = {(x.get("difficulty") or "").upper(): x.get("count", 0)
                   for x in (node.get("numAcceptedQuestions") or [])}
        tags.extend(self._solve_tags(
            easy=by_diff.get("EASY", 0),
            medium=by_diff.get("MEDIUM", 0),
            hard=by_diff.get("HARD", 0),
        ))
        return tags

    # ---------- leetcode.com ----------

    def _fetch_com(self) -> List[VerifiedTag]:
        tags: List[VerifiedTag] = []
        data = self._gql(_COM_QUERY, {"u": self.username})
        node = data.get("matchedUser")
        if not node:
            raise RuntimeError(f"用户不存在或资料非公开: {self.username}")
        prof = node.get("profile") or {}

        tags.append(VerifiedTag(
            "leetcode_profile", "力扣资料", "开发",
            {"username": node.get("username") or self.username,
             "country": prof.get("countryName") or "",
             "globalRanking": prof.get("ranking"),   # .com 这里是标量
             "reputation": prof.get("reputation", 0),
             "githubUrl": node.get("githubUrl") or ""},
            self.source_name))

        if prof.get("skillTags"):
            tags.append(VerifiedTag(
                "leetcode_skill_tags", "技能标签", "开发",
                {"tags": prof["skillTags"][:20]}, self.source_name))

        # 难度分布：排除 All 汇总项，否则总数会翻倍
        stats = {(x.get("difficulty") or ""): x for x in
                 ((node.get("submitStats") or {}).get("acSubmissionNum") or [])}
        tags.extend(self._solve_tags(
            easy=(stats.get("Easy") or {}).get("count", 0),
            medium=(stats.get("Medium") or {}).get("count", 0),
            hard=(stats.get("Hard") or {}).get("count", 0),
            submissions=(stats.get("All") or {}).get("submissions"),
        ))

        cal = node.get("userCalendar") or {}
        if cal:
            tags.append(VerifiedTag(
                "leetcode_streak", "刷题连续性", "开发",
                {"streak": cal.get("streak", 0),
                 "totalActiveDays": cal.get("totalActiveDays", 0),
                 "activeYears": cal.get("activeYears") or []},
                self.source_name))
        return tags

    # ---------- 共用推导 ----------

    def _solve_tags(self, easy: int, medium: int, hard: int,
                    submissions: Optional[int] = None) -> List[VerifiedTag]:
        total = easy + medium + hard
        value: Dict[str, Any] = {
            "total": total, "easy": easy, "medium": medium, "hard": hard,
        }
        if submissions is not None:
            value["totalSubmissions"] = submissions
            if submissions:
                value["acceptanceHint"] = round(total / submissions, 3)

        tags = [VerifiedTag("leetcode_solved", "已解题数", "开发",
                            value, self.source_name)]

        # 难度倾向：hard 占比反映刷题深度而非单纯数量
        if total:
            hard_ratio = hard / total
            if hard_ratio >= 0.25:
                level = "硬核"
            elif hard_ratio >= 0.10:
                level = "进阶"
            else:
                level = "入门"
            tags.append(VerifiedTag(
                "leetcode_difficulty_pref", "刷题深度", "开发",
                {"level": level, "hardRatio": round(hard_ratio, 3)},
                self.source_name))
        return tags


def _to_num(v: Any) -> Any:
    """.cn 的 currentRating 是字符串形式的数字，统一转数值。"""
    if v is None or isinstance(v, (int, float)):
        return v
    try:
        return round(float(v), 1)
    except (TypeError, ValueError):
        return v
