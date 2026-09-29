#!/usr/bin/env python3
"""微信读书适配器。

先纠正原文档的三处事实错误（均已实测）：

1. 「2026 年微信读书官方推出 AI Skill」「weread-mcp 是官方发布的 MCP Server」
   —— 不成立。npm 上 weread-mcp@1.0.0 自己的 description 写的是
   「微信读书 MCP Server (非官方)」，repository 指向个人账号
   github.com/j2st1n/weread-mcp，maintainer 是 rq3zs2wo。
   原文档整节的风险评级建立在「官方支持后风险降低」这一前提上，前提不成立。

2. 文档给的两条内部 API 路径都是 404：
     /user/reading/statistics   404 不存在
     /note/getList              404 不存在
   实际存在（401 需 cookie）的是：
     /shelf/sync                书架
     /readdetail                阅读时长明细
     /user                      用户信息
     /book/notebooks            有笔记的书列表

3. 原 WeReadAdapter 的 mcp 模式假设 http://localhost:3001 上有 REST 端点。
   MCP 是 stdio 上的 JSON-RPC，不是 HTTP REST 服务，该模式无法工作。
   因此本适配器只保留 cookie 直连模式。

Cookie 获取：浏览器登录 weread.qq.com → DevTools → Application → Cookies，
复制整条 Cookie 串（至少含 wr_skey 与 wr_vid）。wr_skey 有效期较短（约数天），
过期表现为 errcode -2012 / -2010，需重新抓取。
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from .base import BaseAdapter, VerifiedTag


class WeReadAdapter(BaseAdapter):
    source_name = "weread"
    BASE_URL = "https://i.weread.qq.com"

    def __init__(self, creds: Dict[str, Any], **kw):
        super().__init__(creds, **kw)
        cookie = self.creds.get("cookie") or ""
        if cookie:
            self.session.headers["Cookie"] = cookie
        self.session.headers.setdefault("baseapi", "32")
        self.session.headers.setdefault("appver", "8.2.5.10163885")

    def missing_credential(self):
        if not self.creds.get("cookie"):
            return ("credentials.json 的 weread.cookie 为空 —— "
                    "浏览器登录 weread.qq.com 后从 DevTools 复制整条 Cookie"
                    "（需含 wr_skey / wr_vid）")
        return None

    def _get(self, path: str, **params) -> Optional[Dict[str, Any]]:
        """返回 None 表示该端点不可用；鉴权失效则抛错（需换 cookie）。"""
        r = self.session.get(f"{self.BASE_URL}{path}",
                             params=params or None, timeout=self.timeout)
        if r.status_code == 404:
            return None
        try:
            d = r.json()
        except ValueError:
            return None
        errcode = d.get("errcode")
        if errcode in (-2010, -2012, -2013):
            raise RuntimeError(
                f"微信读书 cookie 已失效（errcode={errcode} "
                f"errmsg={d.get('errmsg')!r}），请重新抓取 wr_skey")
        return d

    def dump_raw(self) -> Dict[str, Any]:
        """把候选端点的原始响应全取回，用于确认真实字段名。"""
        out: Dict[str, Any] = {}
        for path in ["/user", "/shelf/sync", "/readdetail",
                     "/book/notebooks", "/shelf/friendCommon"]:
            try:
                out[path] = self._get(path)
            except Exception as e:
                out[path] = {"_error": f"{type(e).__name__}: {e}"}
        return out

    def fetch(self) -> List[VerifiedTag]:
        tags: List[VerifiedTag] = []

        # ---------- 1. 书架 ----------
        shelf = self._get("/shelf/sync")
        if shelf:
            books = shelf.get("books") or []
            # 阅读进度字段在书架同步里通常不带，进度要看 bookProgress
            progress = {p.get("bookId"): p for p in (shelf.get("bookProgress") or [])}
            finished = 0
            in_progress = 0
            for b in books:
                bid = b.get("bookId")
                pct = (progress.get(bid) or {}).get("progress")
                if pct is None:
                    continue
                if pct >= 100:
                    finished += 1
                elif pct > 0:
                    in_progress += 1

            cats: Counter = Counter()
            for b in books:
                c = b.get("category") or ""
                # category 形如 "文学-小说"，取一级分类
                if c:
                    cats[c.split("-")[0]] += 1

            tags.append(VerifiedTag(
                "read_book_count", "书架书籍数", "阅读",
                {"count": len(books)}, self.source_name))
            if finished or in_progress:
                tags.extend([
                    VerifiedTag("read_finished_count", "读完数量", "阅读",
                                {"count": finished}, self.source_name),
                    VerifiedTag("read_in_progress", "在读数量", "阅读",
                                {"count": in_progress}, self.source_name),
                ])
            if cats:
                tags.append(VerifiedTag(
                    "read_favorite_categories", "偏好分类", "阅读",
                    {"categories": [c for c, _ in cats.most_common(5)],
                     "distribution": dict(cats.most_common(10))},
                    self.source_name))

        # ---------- 2. 阅读时长 ----------
        detail = self._get("/readdetail", baseTimestamp=0, count=1000, type=1)
        if detail:
            # readdetail 返回按天/周的时长明细，字段名以实际响应为准
            total_seconds = detail.get("totalReadTime") or 0
            datas = detail.get("datas") or detail.get("readTimes") or []
            day_count = len(datas) if isinstance(datas, list) else 0

            if total_seconds:
                tags.append(VerifiedTag(
                    "read_total_hours", "总阅读时长", "阅读",
                    {"hours": round(total_seconds / 3600.0, 1)},
                    self.source_name))
            if day_count:
                if day_count >= 300:
                    level = "硬核"
                elif day_count >= 120:
                    level = "稳定"
                elif day_count >= 30:
                    level = "轻度"
                else:
                    level = "起步"
                tags.append(VerifiedTag(
                    "read_consistency", "阅读坚持度", "阅读",
                    {"level": level, "activeDays": day_count},
                    self.source_name))

            tags.append(VerifiedTag(
                "weread_raw_readdetail_keys", "readdetail 实际字段（诊断用）",
                "诊断", {"keys": sorted(detail.keys())},
                self.source_name, verified=False))

        # ---------- 3. 笔记 ----------
        nb = self._get("/book/notebooks")
        if nb:
            books = nb.get("books") or []
            total_notes = sum((b.get("noteCount") or 0) for b in books)
            total_marks = sum((b.get("bookmarkCount") or 0) for b in books)
            tags.append(VerifiedTag(
                "read_note_count", "笔记数量", "阅读",
                {"noteCount": total_notes,
                 "bookmarkCount": total_marks,
                 "booksWithNotes": len(books)},
                self.source_name))
            if books:
                tags.append(VerifiedTag(
                    "read_highlight_density", "划线密度", "阅读",
                    {"perBook": round((total_notes + total_marks) / len(books), 2)},
                    self.source_name))

        if not tags:
            raise RuntimeError(
                "所有端点都没返回可用数据 —— cookie 可能无效或已过期")
        return tags
