"""导入豆包给的「人格/EGO 卡图直链」并下载到 data/portraits/。

输入：data/portraits/ans/*.json，结构见 scripts/export_portrait_tasks.py 生成的答案模板
      {"items":[{"id":10310,"name":"堂吉诃德","page":"...","image":"https://...png","kind":"卡面","confidence":"high"}]}
输出：data/portraits/identity/<人格id>.png、data/portraits/ego/<EGO id>.png（已存在则不覆盖，除非 --force）

用法：
    python scripts/import_portrait_urls.py --dry-run
    python scripts/import_portrait_urls.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LimbusPatcher/1.0"


def load_items(ans_dir: Path) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    problems: list[str] = []
    for path in sorted(ans_dir.glob("*.json")):
        try:
            obj = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{path.name}: 读取失败（{exc}）")
            continue
        rows = obj.get("items") if isinstance(obj, dict) else obj
        if not isinstance(rows, list):
            problems.append(f"{path.name}: 结构不对（需要 items 数组）")
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                eid = int(row.get("id"))
            except (TypeError, ValueError):
                problems.append(f"{path.name}: 缺少/非法 id（{row.get('id')!r}）")
                continue
            url = str(row.get("image") or "").strip()
            if not url:
                problems.append(f"{path.name}: id={eid} 没有 image（kind={row.get('kind')}）")
                continue
            items.append({"id": eid, "url": url, "kind": row.get("kind") or "",
                          "page": row.get("page") or "", "name": row.get("name") or ""})
    return items, problems


def download(url: str, dest: Path) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://limbuscompany.huijiwiki.com/"})
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = resp.read()
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:80]
    if len(data) < 1024:
        return False, f"内容过小（{len(data)} 字节）"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ans", type=Path, default=ROOT / "data" / "portraits" / "ans")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "portraits")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if not args.ans.is_dir():
        print(f"答案目录不存在：{args.ans}（把豆包回的 JSON 按任务包同名存进去）")
        return 2
    items, problems = load_items(args.ans)
    print(f"解析到 {len(items)} 条直链，问题 {len(problems)} 条")
    ok = skipped = failed = 0
    failures: list[str] = []
    t0 = time.time()
    for it in items:
        sub = "ego" if str(it["id"]).startswith("2") else "identity"
        dest = args.out / sub / f"{it['id']}.png"
        if dest.is_file() and not args.force:
            skipped += 1
            continue
        if args.dry_run:
            ok += 1
            continue
        good, err = download(it["url"], dest)
        if good:
            ok += 1
        else:
            failed += 1
            if len(failures) < 8:
                failures.append(f"  id={it['id']} {err} ← {it['url'][:70]}")
    print(f"{'[dry-run] ' if args.dry_run else ''}下载 {ok}，跳过已存在 {skipped}，失败 {failed}，用时 {time.time() - t0:.1f}s")
    for line in failures:
        print(line)
    if problems[:6]:
        print("问题样例：")
        for p in problems[:6]:
            print("  ⚠", p)
    if failed:
        print("失败的多为灰机 CDN 拦截：可让豆包改用图片页链接，或人工另存到 data/portraits/ 后跑一次本脚本校验")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
