#!/usr/bin/env python3
"""实测入口。

用法：
  python run_probe.py                    # 跑所有源，缺凭证的自动跳过
  python run_probe.py github leetcode    # 只跑指定源
  python run_probe.py --dump keep        # 打印某源的原始响应（用于确认字段名）
  python run_probe.py --creds            # 只看凭证配置状态，不发请求
  python run_probe.py --json out.json    # 结果写入 JSON

凭证放 credentials.json（已 gitignore）。参考 credentials.example.json。
"""
from __future__ import annotations

import argparse
import io
import json
import sys

# Windows 控制台默认 GBK，输出中文/符号会 UnicodeEncodeError，强制 UTF-8
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)

from adapters import (  # noqa: E402
    NO_CREDENTIAL_SOURCES, REGISTRY, create, load_credentials, mask,
)

BAR = "=" * 72


def show_creds(creds: dict) -> None:
    print(BAR)
    print("凭证配置状态")
    print(BAR)
    if not creds:
        print("  未找到 credentials.json")
        print("  → 复制 credentials.example.json 为 credentials.json 后填写\n")

    rows = [
        ("github", "token", "可选（无 token 限速 60/h）"),
        ("steam", "api_key", "必填 → https://steamcommunity.com/dev/apikey"),
        ("duolingo", "username", "无需鉴权"),
        ("leetcode", "username", "无需鉴权"),
        ("keep", "token", "token 或 mobile+password 二选一"),
        ("weread", "cookie", "必填（wr_skey）"),
        ("netease", "cookie", "必填 + 需自建服务"),
    ]
    for src, key, note in rows:
        c = creds.get(src) or {}
        val = c.get(key)
        if src == "keep" and not val:
            val = "(mobile)" if c.get("mobile") else None
        state = f"已配置 {mask(val)}" if val else "未配置"
        print(f"  {src:<10} {key:<10} {state:<22} {note}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("sources", nargs="*", help="要测的数据源，留空则全部")
    ap.add_argument("--dump", metavar="SOURCE",
                    help="打印该源的原始响应（keep / weread 支持）")
    ap.add_argument("--creds", action="store_true", help="只看凭证状态")
    ap.add_argument("--json", metavar="PATH", help="结果写入 JSON 文件")
    args = ap.parse_args()

    creds = load_credentials()

    if args.creds:
        show_creds(creds)
        return 0

    if args.dump:
        src = args.dump
        if src not in REGISTRY:
            print(f"未知数据源: {src}（可用: {sorted(REGISTRY)}）")
            return 2
        adapter = create(src, creds)
        gap = adapter.missing_credential()
        if gap:
            print(f"[跳过] {src}: {gap}")
            return 1
        if not hasattr(adapter, "dump_raw"):
            print(f"{src} 不支持 --dump（仅 keep / weread 支持）")
            return 2
        print(f"{src} 原始响应：")
        print(json.dumps(adapter.dump_raw(), ensure_ascii=False, indent=2)[:12000])
        return 0

    targets = args.sources or list(REGISTRY)
    unknown = [s for s in targets if s not in REGISTRY]
    if unknown:
        print(f"未知数据源: {unknown}（可用: {sorted(REGISTRY)}）")
        return 2

    show_creds(creds)

    results = []
    for src in targets:
        print(BAR)
        print(f"{src}")
        print(BAR)
        try:
            adapter = create(src, creds)
        except Exception as e:
            print(f"  [初始化失败] {type(e).__name__}: {e}\n")
            continue

        res = adapter.run()
        results.append(res)

        if res.skipped_reason:
            print(f"  [跳过] {res.skipped_reason}\n")
            continue
        if not res.ok:
            print(f"  [失败] {res.error}  ({res.latency_ms}ms)\n")
            continue

        print(f"  [成功] {len(res.tags)} 个标签  ({res.latency_ms}ms)")
        for t in res.tags:
            v = json.dumps(t.value, ensure_ascii=False)
            if len(v) > 150:
                v = v[:150] + "…"
            flag = "" if t.verified else "  [诊断]"
            print(f"    · {t.name} ({t.tag_id}){flag}\n        {v}")
        print()

    # ---------- 汇总 ----------
    print(BAR)
    print("汇总")
    print(BAR)
    ok = [r for r in results if r.ok]
    skipped = [r for r in results if r.skipped_reason]
    failed = [r for r in results if not r.ok and not r.skipped_reason]

    for r in results:
        if r.ok:
            state = f"成功  {len(r.tags):>2} 标签  {r.latency_ms:>5}ms"
        elif r.skipped_reason:
            state = "跳过  缺凭证"
        else:
            state = f"失败  {(r.error or '')[:50]}"
        print(f"  {r.source:<14} {state}")

    total_tags = sum(len(r.tags) for r in ok)
    print(f"\n  成功 {len(ok)} 源 / 跳过 {len(skipped)} / 失败 {len(failed)}"
          f"，共 {total_tags} 个标签")

    if skipped:
        print(f"\n  待补凭证: {', '.join(r.source for r in skipped)}")
    if not creds:
        print(f"  无凭证也能跑的源: {', '.join(NO_CREDENTIAL_SOURCES)}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump([r.to_dict() for r in results], f,
                      ensure_ascii=False, indent=2)
        print(f"\n  结果已写入 {args.json}")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
