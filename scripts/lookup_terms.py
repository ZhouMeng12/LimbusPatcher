"""查词：给定英文词，打印术语表命中 + 旧章节英中证据（定译用）。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "data" / "translate"
terms = json.loads((WORK / "glossary.json").read_text(encoding="utf-8"))
gl, spk = terms.get("terms") or {}, terms.get("speakers") or {}
pairs = [json.loads(l) for l in (WORK / "范例行对.jsonl").read_text(encoding="utf-8").splitlines()]

words = sys.argv[1:]
for w in words:
    if w.startswith("model:"):
        m = w.split(":", 1)[1]
        s = spk.get(m)
        print(f"[说话人] {m} → {s['teller_zh'] if s else '（无）'}"
              f"（en={s['teller_en'] if s else ''}, n={s['n'] if s else 0}）")
        continue
    hit = gl.get(w) or next((v for k, v in gl.items() if k.lower() == w.lower()), None)
    print(f"[术语] {w} → {hit['zh'] if hit else '（表里没有）'}"
          + (f"  [{hit['kind']} {hit['file']}#{hit['id']}]" if hit else ""))
    ev = [p for p in pairs if w in p["en"]][:3]
    for p in ev:
        print(f"    证据 {p['file']}#{p['id']}: {p['en'][:110]}")
        print(f"         → {p['zh'][:70]}")
