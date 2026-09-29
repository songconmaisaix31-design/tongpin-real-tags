#!/usr/bin/env python3
"""数据源适配器公共基础设施。

对应 DataSourceAdapter_Interface.md 的 IDataSourceAdapter，用 Python 表达。
只保留实测需要的部分：凭证加载、统一标签结构、HTTP 会话、健康检查。
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRED_PATH = os.path.join(REPO_ROOT, "credentials.json")


def utc_now_iso() -> str:
    """时区感知的 UTC 时间戳。

    注意：不要用 datetime.utcnow()——它返回 naive datetime，与 aware datetime
    做减法会抛 TypeError（原 Keep 示例代码就是栽在这里）。
    """
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(ts: str) -> datetime:
    """解析 ISO 8601 时间戳为 **时区感知** 的 datetime。

    原示例代码写的是 fromisoformat(ts.replace("Z", ""))，那样会丢掉 UTC 标记
    得到 naive datetime，再调 .timestamp() 会按本机时区解释，在 UTC+8 下
    产生 8 小时偏移。这里统一转成 +00:00。
    """
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def days_since(ts: str) -> int:
    """距今天数。两侧都是 aware datetime，可安全相减。"""
    created = parse_iso(ts)
    return (datetime.now(timezone.utc) - created).days


@dataclass
class VerifiedTag:
    """统一标签结构，对应接口文档第 1 节 VerifiedTag。"""

    tag_id: str
    name: str
    category: str
    value: Dict[str, Any]
    source: str
    verified: bool = True
    visibility: str = "self_only"
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tagId": self.tag_id,
            "name": self.name,
            "category": self.category,
            "value": self.value,
            "source": self.source,
            "verified": self.verified,
            "visibility": self.visibility,
            "updatedAt": self.updated_at,
        }


@dataclass
class FetchResult:
    """一次拉取的结果，含成功/失败与诊断信息。"""

    source: str
    ok: bool
    tags: List[VerifiedTag] = field(default_factory=list)
    error: Optional[str] = None
    skipped_reason: Optional[str] = None
    latency_ms: int = 0
    fetched_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "ok": self.ok,
            "tags": [t.to_dict() for t in self.tags],
            "error": self.error,
            "skippedReason": self.skipped_reason,
            "latencyMs": self.latency_ms,
            "fetchedAt": self.fetched_at,
        }


def load_credentials(path: str = CRED_PATH) -> Dict[str, Any]:
    """读取 credentials.json。文件不存在时返回空字典（各适配器会各自跳过）。"""
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    # 去掉以 _ 开头的说明性键
    return {
        k: ({ik: iv for ik, iv in v.items() if not ik.startswith("_")}
            if isinstance(v, dict) else v)
        for k, v in raw.items()
        if not k.startswith("_")
    }


def mask(secret: Optional[str], keep: int = 4) -> str:
    """脱敏显示凭证，供日志使用。绝不打印完整值。"""
    if not secret:
        return "<空>"
    s = str(secret)
    if len(s) <= keep:
        return "*" * len(s)
    return s[:keep] + "*" * min(len(s) - keep, 8)


class BaseAdapter:
    """适配器基类。子类实现 fetch()，返回 List[VerifiedTag]。"""

    source_name: str = "base"
    default_timeout: int = 20

    def __init__(self, creds: Dict[str, Any], timeout: Optional[int] = None):
        self.creds = creds or {}
        self.timeout = timeout or self.default_timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        })

    # ---------- 子类需要实现 ----------

    def missing_credential(self) -> Optional[str]:
        """返回缺失凭证的说明；返回 None 表示凭证齐备。"""
        return None

    def fetch(self) -> List[VerifiedTag]:
        raise NotImplementedError

    # ---------- 通用流程 ----------

    def run(self) -> FetchResult:
        """带计时、凭证检查与异常兜底的执行入口。单源失败不影响其他源。"""
        gap = self.missing_credential()
        if gap:
            return FetchResult(source=self.source_name, ok=False, skipped_reason=gap)

        t0 = time.time()
        try:
            tags = self.fetch()
            return FetchResult(
                source=self.source_name,
                ok=True,
                tags=tags,
                latency_ms=int((time.time() - t0) * 1000),
            )
        except Exception as e:  # noqa: BLE001 — 单源隔离，故意宽捕获
            return FetchResult(
                source=self.source_name,
                ok=False,
                error=f"{type(e).__name__}: {e}",
                latency_ms=int((time.time() - t0) * 1000),
            )

    def get_json(self, url: str, **kw) -> Any:
        kw.setdefault("timeout", self.timeout)
        r = self.session.get(url, **kw)
        r.raise_for_status()
        return r.json()

    def post_json(self, url: str, **kw) -> Any:
        kw.setdefault("timeout", self.timeout)
        r = self.session.post(url, **kw)
        r.raise_for_status()
        return r.json()
