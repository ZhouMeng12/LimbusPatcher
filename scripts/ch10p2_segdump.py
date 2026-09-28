# -*- coding: utf-8 -*-
"""导出路线 A/B 各楼层对话文件的记录摘要，供分段定位使用。"""
import io, json, os

ROOT = r"D:\Desktop\lbc"
SRC = os.path.join(ROOT, "data", "translate", "files", "RPGSystem")
DST = os.path.join(ROOT, "temp", "segdump")
if not os.path.isdir(DST):
    os.makedirs(DST)

FILES = [
    # 路线 B
    "rpg-loc-dialogue-floor-1-b.json",
    "rpg-loc-dialogue-floor-2-b.json",
    "rpg-loc-dialogue-floor-3-b.json",
    "rpg-loc-dialogue-floor-4-b.json",
    "rpg-loc-dialogue-floor-5-b.json",
    "rpg-loc-dialogue-floor-b1-b.json",
    "rpg-loc-dialogue-floor-b2-b.json",
    "rpg-loc-dialogue-floor-b3-b.json",
    # 路线 A
    "rpg-loc-dialogue-floor-1.json",
    "rpg-loc-dialogue-floor-2.json",
    "rpg-loc-dialogue-floor-3.json",
    "rpg-loc-dialogue-floor-4.json",
    "rpg-loc-dialogue-floor-b1.json",
    "rpg-loc-dialogue-floor-b2.json",
    "rpg-loc-dialogue-route-a.json",
]

for fn in FILES:
    p = os.path.join(SRC, fn)
    if not os.path.exists(p):
        continue
    d = json.load(io.open(p, encoding="utf-8"))
    dl = d.get("dataList", [])
    out = io.open(os.path.join(DST, fn.replace(".json", ".txt")), "w", encoding="utf-8")
    out.write("FILE=%s  records=%d\n\n" % (fn, len(dl)))
    for i, it in enumerate(dl):
        key = it.get("key", "")
        texts = it.get("texts", [])
        head = texts[0] if texts else {}
        speaker = head.get("speaker", "")
        text = (head.get("text", "") or "").replace("\n", " ")[:70]
        n = len(texts)
        out.write("[%3d] %-8s %-10s (%d行) %s\n" % (i, key, speaker, n, text))
    out.close()
print("dumped to", DST)
