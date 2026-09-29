#!/usr/bin/env python3
"""Keep 运动适配器。

实测结论（无凭证即可确认）：
  /pd/v3/stats/detail            401 → 存在，需鉴权
  /pd/v3/runninglog/{id}         401 → 存在
  /pd/v3/cyclinglog/{id}         401 → 存在
  /pd/v3/yogalog/{id}            401 → 存在
  /pd/v3/hikinglog/{id}          401 → 存在
  /pd/v3/traininglog/{id}        401 → 存在
  /pd/v3/stats/records           404 → **不存在**（原文档写错了）

原文档用 stats/records 推导 sport_primary_type / sport_active_time /
sport_consecutive_weeks 三个标签，该接口不存在，这三个标签需改由
stats/detail 的返回内容推导。stats/detail 具体返回结构需 token 才能确认，
因此本适配器提供 dump_raw() 供拿到 token 后直接查看原始结构，
再据此补全推导逻辑（见 fetch 中标注的 TODO 段）。

原示例代码的另一个 bug：fetch_records 用 data.get("code") == 0 判定成功，
但 Keep 实际响应键是 ['data','errorCode','now','ok','text','version']，
没有 code 字段，该分支永远为假。本文件统一用 ok 判定。
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any, Dict, List, Optional

from .base import BaseAdapter, VerifiedTag, mask

SPORT_TYPES = ["running", "cycling", "hiking", "training", "yoga"]


class KeepAdapter(BaseAdapter):
    source_name = "keep"
    BASE_URL = "https://api.gotokeep.com"

    def __init__(self, creds: Dict[str, Any], **kw):
        super().__init__(creds, **kw)
        self.token = self.creds.get("token") or ""
        self.mobile = self.creds.get("mobile") or ""
        self.password = self.creds.get("password") or ""
        self.country_code = str(self.creds.get("country_code") or "86")
        self.user_id: Optional[str] = None
        self.session.headers["User-Agent"] = (
            "Keep/7.25.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)"
        )
        if self.token:
            self._apply_token(self.token)

    def missing_credential(self):
        if not self.token and not (self.mobile and self.password):
            return ("Keep 需要凭证：填 keep.token（推荐，抓包取 Authorization），"
                    "或填 keep.mobile + keep.password")
        return None

    def _apply_token(self, token: str) -> None:
        self.token = token
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        })

    # ---------- 认证 ----------

    def login(self) -> bool:
        """手机号+密码登录。

        实测线索（用假号码做的字段校验探测，非撞库）：
          只传 mobile          → 400 "password required"
          补上 password        → 400 errorCode 100001 "账号与密码不匹配"
        服务端在做凭证比对而不是报解密失败，说明明文在传输层被接受。
        但这不排除服务端对收到的值再做哈希 —— 若真实账号密码明文登录失败，
        再考虑 SHA256 / RSA 预处理。
        """
        url = f"{self.BASE_URL}/v1.1/users/login"
        payload = {
            "mobile": self.mobile,
            "password": self.password,
            "countryCode": self.country_code,
        }
        r = self.session.post(
            url, json=payload, timeout=self.timeout,
            headers={"Content-Type": "application/json; charset=utf-8"})
        try:
            d = r.json()
        except ValueError:
            raise RuntimeError(f"登录响应非 JSON: HTTP {r.status_code} {r.text[:200]}")

        if not d.get("ok"):
            raise RuntimeError(
                f"登录失败 errorCode={d.get('errorCode')} "
                f"text={d.get('text')} data={d.get('data')}")

        data = d.get("data") or {}
        token = data.get("token")
        if not token:
            raise RuntimeError(f"登录成功但响应无 token，data 键={sorted(data.keys())}")
        self._apply_token(token)
        self.user_id = data.get("userId") or data.get("id")
        return True

    def ensure_auth(self) -> None:
        if not self.token:
            self.login()

    # ---------- 数据拉取 ----------

    def fetch_stats_detail(self, sport_type: str) -> Optional[Dict[str, Any]]:
        """统一用 ok 字段判定成功（不是 code）。404/401 返回 None 而非抛错。"""
        r = self.session.get(f"{self.BASE_URL}/pd/v3/stats/detail",
                             params={"dateUnit": "all", "type": sport_type},
                             timeout=self.timeout)
        try:
            d = r.json()
        except ValueError:
            return None
        if not d.get("ok"):
            if d.get("errorCode") == 100010:
                raise RuntimeError(
                    "Keep token 已失效（errorCode 100010「账号出了点问题，请重新登录」），"
                    "请重新抓包更新 keep.token")
            return None
        return d.get("data") or {}

    def dump_raw(self) -> Dict[str, Any]:
        """把各运动类型的 stats/detail 原始响应全部取回。

        stats/records 不存在，活跃时段等标签的推导依据要从这里的实际结构里找。
        拿到 token 后先跑 `python run_probe.py --dump keep` 看这个输出。
        """
        self.ensure_auth()
        out: Dict[str, Any] = {}
        for st in SPORT_TYPES:
            try:
                out[st] = self.fetch_stats_detail(st)
            except Exception as e:
                out[st] = {"_error": f"{type(e).__name__}: {e}"}
        return out

    def fetch(self) -> List[VerifiedTag]:
        self.ensure_auth()
        tags: List[VerifiedTag] = []

        stats: Dict[str, Dict[str, Any]] = {}
        for st in SPORT_TYPES:
            d = self.fetch_stats_detail(st)
            if d:
                stats[st] = d

        if not stats:
            raise RuntimeError(
                "所有运动类型的 stats/detail 都没返回数据 —— token 可能无效")

        # stats/detail 的字段名与单位都需 token 实测确认。
        # 这里只做「按候选名取值 + 记录命中的字段名」，**不做单位换算**。
        #
        # 为什么不猜单位：曾写成 `x/1000 if x > 1000 else x` 来兼容米/公里，
        # 但这是按数值大小猜量纲 —— 500 米的跑步会被记成 500 公里，
        # 而以公里为单位的 2000 公里累计值会被除成 2 公里。
        # 这类静默错值比直接报错更难发现（正是 GitHub 适配器原 bug 的形态），
        # 所以宁可原样上报 + 标为诊断，等 --dump 确认单位后再补换算。
        def pick(d: Dict[str, Any], *names):
            """返回 (值, 命中的字段名)；都没命中返回 (None, None)。"""
            for n in names:
                if d.get(n) is not None:
                    return d[n], n
            return None, None

        raw_metrics: Dict[str, Dict[str, Any]] = {}
        count_by_type: Counter = Counter()

        for st, d in stats.items():
            dist, dist_field = pick(d, "totalDistance", "distance",
                                    "totalKmDistance")
            dur, dur_field = pick(d, "totalDuration", "duration", "totalTime")
            cnt, cnt_field = pick(d, "totalCount", "count", "times",
                                  f"total{st.capitalize()}Count")
            raw_metrics[st] = {
                "distance": {"value": dist, "field": dist_field},
                "duration": {"value": dur, "field": dur_field},
                "count": {"value": cnt, "field": cnt_field},
            }
            if cnt is not None:
                try:
                    count_by_type[st] = int(cnt)
                except (TypeError, ValueError):
                    pass

        # 次数是无量纲的，可以直接用
        if count_by_type:
            tags.append(VerifiedTag(
                "sport_primary_type", "主要运动类型", "运动",
                {"type": count_by_type.most_common(1)[0][0],
                 "distribution": dict(count_by_type)},
                self.source_name))
            tags.append(VerifiedTag(
                "sport_total_count", "累计运动次数", "运动",
                {"count": sum(count_by_type.values())}, self.source_name))

        # 距离/时长：单位未确认，原样上报并标为诊断，不进匹配算法
        tags.append(VerifiedTag(
            "keep_raw_metrics", "距离/时长原始值（单位待确认，诊断用）", "诊断",
            raw_metrics, self.source_name, verified=False))

        # 原始结构留档，便于人工核对字段名
        tags.append(VerifiedTag(
            "keep_raw_stats_keys", "stats/detail 实际字段（诊断用）", "诊断",
            {st: sorted(d.keys()) for st, d in stats.items()},
            self.source_name, verified=False))

        # TODO(需 token 实测): sport_active_time / sport_consecutive_weeks /
        # sport_weekly_freq / sport_intensity 原依赖 stats/records（不存在）。
        # 待 dump_raw() 确认 stats/detail 是否内嵌单次记录列表后补全。
        return tags
