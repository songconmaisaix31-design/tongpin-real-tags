"""数据源适配器集合。

对应 DataSourceAdapter_Interface.md 第 5 节的工厂 + 注册机制。
"""
from .base import (
    BaseAdapter,
    FetchResult,
    VerifiedTag,
    load_credentials,
    mask,
    utc_now_iso,
)
from .duolingo_adapter import DuolingoAdapter
from .github_adapter import GitHubAdapter
from .keep_adapter import KeepAdapter
from .leetcode_adapter import LeetCodeAdapter
from .netease_adapter import NetEaseAdapter
from .steam_adapter import SteamAdapter
from .weread_adapter import WeReadAdapter

# 注册表：源名 → (适配器类, credentials.json 中的键)
REGISTRY = {
    "github": (GitHubAdapter, "github"),
    "steam": (SteamAdapter, "steam"),
    "duolingo": (DuolingoAdapter, "duolingo"),
    "leetcode": (LeetCodeAdapter, "leetcode"),
    "keep": (KeepAdapter, "keep"),
    "weread": (WeReadAdapter, "weread"),
    "netease": (NetEaseAdapter, "netease"),
}

# 无需任何凭证即可跑通的源
NO_CREDENTIAL_SOURCES = ["duolingo", "leetcode"]


def create(source: str, creds: dict) -> BaseAdapter:
    if source not in REGISTRY:
        raise ValueError(f"未知数据源: {source}（可用: {sorted(REGISTRY)}）")
    cls, key = REGISTRY[source]
    return cls(creds.get(key) or {})


__all__ = [
    "BaseAdapter", "FetchResult", "VerifiedTag", "REGISTRY",
    "NO_CREDENTIAL_SOURCES", "create", "load_credentials", "mask",
    "utc_now_iso",
    "DuolingoAdapter", "GitHubAdapter", "KeepAdapter", "LeetCodeAdapter",
    "NetEaseAdapter", "SteamAdapter", "WeReadAdapter",
]
