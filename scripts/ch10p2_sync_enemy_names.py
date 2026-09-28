# -*- coding: utf-8 -*-
"""敌人中文名同步（以零协译名为准）。

stage_enemies.json 里的名字上一轮已按零协术语统一过；译文文件
data/translate/files/Enemies-a1c10p1/p2.json 里仍是自译名，本脚本把译文
对齐到 stage_enemies（也就是零协译名），保证「软件列表」与「游戏内显示」一致。

用法： python scripts/ch10p2_sync_enemy_names.py [--apply]
"""
import io
import json
import os
import sys

ROOT = r"D:\Desktop\lbc"
OUT = os.path.join(ROOT, "_enemy_sync.txt")


def load(p):
    return json.load(io.open(p, encoding="utf-8"))


def stage_names():
    se = load(os.path.join(ROOT, "limbus_patcher", "data", "stage_enemies.json"))
    m = {}
    for ch in se.get("chapters", []):
        for st in ch.get("stages", []):
            for e in st.get("enemies", []):
                if e.get("id") is not None and e.get("name"):
                    m.setdefault(int(e["id"]), e["name"])
        for e in ch.get("chapter_enemies", []):
            if e.get("id") is not None and e.get("name"):
                m.setdefault(int(e["id"]), e["name"])
    return m


def main():
    apply = "--apply" in sys.argv
    out = io.open(OUT, "w", encoding="utf-8", buffering=1)
    names = stage_names()
    out.write("零协敌人名（stage_enemies）%d 条\n" % len(names))
    changed = 0
    for fn in ("Enemies-a1c10p1.json", "Enemies-a1c10p2.json"):
        p = os.path.join(ROOT, "data", "translate", "files", fn)
        if not os.path.exists(p):
            continue
        d = load(p)
        touched = False
        for it in d.get("dataList", []):
            i = it.get("id")
            try:
                i = int(i)
            except (TypeError, ValueError):
                continue
            if i in names and it.get("name") != names[i]:
                out.write("  %s %s: %s -> %s\n" % (fn, i, it.get("name"), names[i]))
                if apply:
                    it["name"] = names[i]
                changed += 1
                touched = True
        if apply and touched:
            io.open(p, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=2))
    out.write("changed=%d\n" % changed)
    out.close()


if __name__ == "__main__":
    main()
