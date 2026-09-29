#!/usr/bin/env python3
"""网易云音乐适配器（基于自建 NeteaseCloudMusicApi 服务）。

实测提醒：原文档依赖的 Binaryify/NeteaseCloudMusicApi 已归档
（archived=true，最后提交 2024-02-28），而文档「替代项目」一栏填的
是同一个归档仓库的同一个 URL，属于自我循环。请换活跃 fork 部署。

原文档的另一处不一致：正文接口清单写 POST，Python 示例代码用 GET。
本适配器统一用 POST（该服务两种方法都接受，但 POST 可避免 URL 长度
与 CDN 缓存问题，官方文档也推荐 POST）。
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from .base import BaseAdapter, VerifiedTag

VIP_NAMES = {0: "普通", 10: "月度会员", 11: "黑胶VIP"}


class NetEaseAdapter(BaseAdapter):
    source_name = "netease_music"

    def __init__(self, creds: Dict[str, Any], **kw):
        super().__init__(creds, **kw)
        self.base_url = (self.creds.get("base_url") or "").rstrip("/")
        self.uid = str(self.creds.get("uid") or "")
        self.cookie = self.creds.get("cookie") or ""

    def missing_credential(self):
        if not self.base_url:
            return ("credentials.json 的 netease.base_url 为空 —— "
                    "需自行部署 NeteaseCloudMusicApi（原仓库已归档，请用活跃 fork）")
        if not self.uid:
            return "netease.uid 为空（在网易云个人主页 URL 里可看到）"
        if not self.cookie:
            return ("netease.cookie 为空 —— 听歌记录属私有数据，"
                    "需登录后的 MUSIC_U cookie")
        return None

    def _post(self, path: str, **params) -> Optional[Dict[str, Any]]:
        """统一 POST。cookie 通过 body 传（该服务支持），避免代理丢 header。"""
        payload = dict(params)
        if self.cookie:
            payload["cookie"] = self.cookie
        try:
            r = self.session.post(f"{self.base_url}{path}",
                                  data=payload, timeout=self.timeout)
        except Exception as e:
            raise RuntimeError(
                f"连不上 {self.base_url} —— 服务是否已启动？({type(e).__name__})")
        try:
            d = r.json()
        except ValueError:
            return None
        code = d.get("code")
        if code in (301, 302):
            raise RuntimeError(
                f"网易云未登录/cookie 失效（code={code}），请更新 netease.cookie")
        return d

    def fetch(self) -> List[VerifiedTag]:
        tags: List[VerifiedTag] = []

        # ---------- 1. 用户资料 ----------
        d = self._post("/user/detail", uid=self.uid)
        if d and d.get("code") == 200:
            prof = d.get("profile") or {}
            vip = prof.get("vipType", 0)
            tags.append(VerifiedTag(
                "music_vip_status", "会员状态", "音乐",
                {"vipType": vip, "typeName": VIP_NAMES.get(vip, f"其他({vip})")},
                self.source_name))
            tags.append(VerifiedTag(
                "music_social", "音乐社交活跃度", "音乐",
                {"followeds": prof.get("followeds", 0),
                 "follows": prof.get("follows", 0),
                 "playlistBeSubscribedCount":
                     prof.get("playlistBeSubscribedCount", 0)},
                self.source_name))
            # level 在 /user/detail 里就有，不必再单独请求 /user/level
            if d.get("level") is not None:
                tags.append(VerifiedTag(
                    "music_level", "音乐等级", "音乐",
                    {"level": d.get("level")}, self.source_name))

        # ---------- 2. 听歌记录 ----------
        # type=1 是全部（allData），type=0 是最近一周（weekData）
        d = self._post("/user/record", uid=self.uid, type=1)
        if d and d.get("code") == 200:
            records = d.get("allData") or d.get("weekData") or []
            artists: Counter = Counter()
            durations: List[float] = []
            total_plays = 0

            for r in records:
                song = r.get("song") or {}
                total_plays += r.get("playCount", 0)
                for a in (song.get("ar") or song.get("artists") or []):
                    if a.get("name"):
                        artists[a["name"]] += 1
                dur = song.get("dt") or song.get("duration") or 0
                if dur:
                    durations.append(dur / 1000.0)

            if artists:
                tags.append(VerifiedTag(
                    "music_top_artists", "常听歌手", "音乐",
                    {"artists": [a for a, _ in artists.most_common(5)]},
                    self.source_name))
                tags.append(VerifiedTag(
                    "music_artist_diversity", "听歌广度", "音乐",
                    {"uniqueArtists": len(artists), "sampledSongs": len(records)},
                    self.source_name))
            if durations:
                tags.append(VerifiedTag(
                    "music_avg_song_length", "偏好歌曲长度", "音乐",
                    {"avgSeconds": round(sum(durations) / len(durations))},
                    self.source_name))
            tags.append(VerifiedTag(
                "music_listening_intensity", "听歌强度", "音乐",
                {"totalPlayCount": total_plays, "sampledSongs": len(records)},
                self.source_name))

        # ---------- 3. 歌单 ----------
        d = self._post("/user/playlist", uid=self.uid, limit=50)
        if d and d.get("code") == 200:
            pls = d.get("playlist") or []
            created = [p for p in pls if str(p.get("userId")) == str(self.uid)]
            tags.append(VerifiedTag(
                "music_playlist_stats", "歌单情况", "音乐",
                {"total": len(pls), "created": len(created),
                 "names": [p.get("name") for p in created[:10]]},
                self.source_name))

        if not tags:
            raise RuntimeError("所有端点都没返回可用数据 —— 检查服务与 cookie")
        return tags
