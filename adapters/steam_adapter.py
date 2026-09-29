#!/usr/bin/env python3
"""Steam 适配器。

接口清单已实测：文档列的 7 个端点全部真实存在（用伪造 key 得 401/403，
对照组不存在的端点得 404）。需要 API Key 才能验证响应字段结构。

注意：playtime_forever / playtime_2weeks 单位是 **分钟**，不是小时。
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from .base import BaseAdapter, VerifiedTag, days_since


class SteamAdapter(BaseAdapter):
    source_name = "steam"
    BASE_URL = "https://api.steampowered.com"

    def __init__(self, creds: Dict[str, Any], **kw):
        super().__init__(creds, **kw)
        self.api_key = self.creds.get("api_key") or ""
        self.steam_id = str(self.creds.get("steam_id64") or "")
        self.vanity = self.creds.get("vanity_url") or ""

    def missing_credential(self):
        if not self.api_key:
            return ("credentials.json 的 steam.api_key 为空 —— "
                    "去 https://steamcommunity.com/dev/apikey 申请（域名填 localhost）")
        if not self.steam_id and not self.vanity:
            return "steam.steam_id64 与 steam.vanity_url 至少填一个"
        return None

    def _params(self, **extra) -> Dict[str, Any]:
        p = {"key": self.api_key}
        p.update(extra)
        return p

    def steam_get(self, path: str, **params) -> Any:
        """带 Steam 专属错误翻译的 GET。

        Steam 用 HTTP 状态码而非 JSON 错误体表达失败，且返回的是 HTML，
        直接抛 HTTPError 对使用者没有指导性，这里翻译成可行动的提示。
        """
        r = self.session.get(f"{self.BASE_URL}{path}",
                             params=self._params(**params), timeout=self.timeout)
        if r.status_code in (401, 403):
            raise RuntimeError(
                f"Steam 鉴权失败（HTTP {r.status_code}，{path}）——"
                " api_key 无效/已吊销，或该用户的社区资料未设为公开。"
                " key 申请：https://steamcommunity.com/dev/apikey")
        if r.status_code == 429:
            raise RuntimeError(
                "Steam 限流（HTTP 429）—— 降低调用频率后重试")
        if r.status_code == 400:
            raise RuntimeError(
                f"Steam 请求参数不正确（HTTP 400，{path}）——"
                " 检查 steam_id64 是否为 17 位数字")
        r.raise_for_status()
        try:
            return r.json()
        except ValueError:
            raise RuntimeError(
                f"Steam 返回非 JSON（{path}）：{r.text[:120]}")

    def resolve_steam_id(self) -> str:
        """vanity_url → SteamID64。已有 steam_id64 则直接返回。"""
        if self.steam_id:
            return self.steam_id
        d = self.steam_get("/ISteamUser/ResolveVanityURL/v1/",
                           vanityurl=self.vanity)
        resp = d.get("response", {})
        if resp.get("success") != 1 or not resp.get("steamid"):
            raise RuntimeError(f"vanity_url 解析失败: {resp}")
        self.steam_id = str(resp["steamid"])
        return self.steam_id

    def fetch(self) -> List[VerifiedTag]:
        sid = self.resolve_steam_id()
        tags: List[VerifiedTag] = []

        # ---------- 1. 基本资料 ----------
        d = self.steam_get("/ISteamUser/GetPlayerSummaries/v2/", steamids=sid)
        players = d.get("response", {}).get("players", [])
        if not players:
            raise RuntimeError(
                "GetPlayerSummaries 返回空 —— SteamID64 是否正确？")
        p = players[0]

        # communityvisibilitystate: 3=公开，其他=非公开。非公开时游戏库读不到。
        visibility = p.get("communityvisibilitystate")
        is_public = visibility == 3

        tags.append(VerifiedTag("steam_country", "所在地区", "基础",
                                {"country": p.get("loccountrycode")
                                 or p.get("countrycode") or ""},
                                self.source_name))
        if p.get("timecreated"):
            from datetime import datetime, timezone
            created = datetime.fromtimestamp(p["timecreated"], tz=timezone.utc)
            age_days = (datetime.now(timezone.utc) - created).days
            tags.append(VerifiedTag("steam_account_age", "Steam 账号年龄", "游戏",
                                    {"days": age_days,
                                     "createdAt": created.isoformat()},
                                    self.source_name))

        if not is_public:
            tags.append(VerifiedTag(
                "steam_profile_private", "资料未公开", "游戏",
                {"communityvisibilitystate": visibility,
                 "note": "游戏库/时长需将社区资料设为公开才能读取"},
                self.source_name, verified=False))
            return tags

        # ---------- 2. 游戏库与时长（核心） ----------
        d = self.steam_get("/IPlayerService/GetOwnedGames/v1/",
                           steamid=sid, include_appinfo=1,
                           include_played_free_games=1)
        resp = d.get("response", {})
        games = resp.get("games", []) or []

        # 单位是分钟 → 转小时
        total_hours = sum(g.get("playtime_forever", 0) for g in games) / 60.0
        recent_hours = sum(g.get("playtime_2weeks", 0) for g in games) / 60.0
        played = [g for g in games if g.get("playtime_forever", 0) > 0]
        top = sorted(games, key=lambda g: g.get("playtime_forever", 0),
                     reverse=True)[:10]

        tags.extend([
            VerifiedTag("steam_total_games", "拥有游戏数", "游戏",
                        {"count": resp.get("game_count", len(games)),
                         "playedCount": len(played)}, self.source_name),
            VerifiedTag("steam_total_hours", "总游玩时长", "游戏",
                        {"hours": round(total_hours, 1)}, self.source_name),
            VerifiedTag("steam_recent_active", "近两周活跃度", "游戏",
                        {"hours": round(recent_hours, 1)}, self.source_name),
            VerifiedTag("steam_top_games", "主要游玩游戏", "游戏",
                        {"games": [{"name": g.get("name"),
                                    "hours": round(g.get("playtime_forever", 0) / 60.0, 1)}
                                   for g in top]}, self.source_name),
        ])

        # ---------- 3. 等级与徽章 ----------
        try:
            d = self.steam_get("/IPlayerService/GetSteamLevel/v1/", steamid=sid)
            level = d.get("response", {}).get("player_level")
            if level is not None:
                tags.append(VerifiedTag("steam_level", "Steam 等级", "游戏",
                                        {"level": level}, self.source_name))
        except Exception:
            pass  # 非核心标签，失败不影响整体

        try:
            d = self.steam_get("/IPlayerService/GetBadges/v1/", steamid=sid)
            resp = d.get("response", {})
            tags.append(VerifiedTag("steam_badge_count", "徽章数", "游戏",
                                    {"count": len(resp.get("badges", []) or []),
                                     "playerXp": resp.get("player_xp", 0)},
                                    self.source_name))
        except Exception:
            pass

        # ---------- 4. 近期游玩 ----------
        try:
            d = self.steam_get("/IPlayerService/GetRecentlyPlayedGames/v1/",
                               steamid=sid, count=10)
            recent = d.get("response", {}).get("games", []) or []
            if recent:
                tags.append(VerifiedTag(
                    "steam_recent_games", "近期在玩", "游戏",
                    {"games": [{"name": g.get("name"),
                                "hours2w": round(g.get("playtime_2weeks", 0) / 60.0, 1)}
                               for g in recent]}, self.source_name))
        except Exception:
            pass

        return tags
