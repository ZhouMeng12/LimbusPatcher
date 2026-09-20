"""第十章（新章节）文本勘察：英文基线里有什么、零协包里缺什么、量有多大。

只读，不改任何东西。
"""
import json
import re
from collections import Counter
from pathlib import Path

G = Path("D:/SteamLibrary/steamapps/common/Limbus Company/LimbusCompany_Data")
EN = G / "Assets/Resources_moved/Localize/en"
ZH = G / "Lang/LLC_zh-CN"


def load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return None


def leaves(obj, out=None):
    if out is None:
        out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("id", "model"):
                continue
            leaves(v, out)
    elif isinstance(obj, list):
        for v in obj:
            leaves(v, out)
    elif isinstance(obj, str) and obj.strip():
        out.append(obj)
    return out


def report(root: Path, label: str, pattern: str) -> dict:
    files = sorted(p for p in root.rglob("*.json") if re.search(pattern, p.name))
    print(f"\n=== {label}：匹配 {pattern} 的文件 {len(files)} 个 ===")
    total_leaves = total_chars = 0
    speakers = Counter()
    for p in files[:40]:
        data = load(p)
        dl = (data or {}).get("dataList") if isinstance(data, dict) else None
        if not isinstance(dl, list):
            print(f"  {p.name}: 结构异常")
            continue
        lv = leaves(dl)
        chars = sum(len(x) for x in lv)
        total_leaves += len(lv)
        total_chars += chars
        spk = Counter(str(r.get("teller") or r.get("model") or "") for r in dl if isinstance(r, dict))
        speakers.update({k: v for k, v in spk.items() if k and k != "None"})
        print(f"  {p.name}: 记录 {len(dl)} · 文本叶子 {len(lv)} · 字符 {chars} · 说话人 {len(spk)}")
    print(f"  合计：叶子 {total_leaves} · 字符 {total_chars} · 说话人 {len(speakers)}")
    if speakers:
        print("  说话人 top:", speakers.most_common(8))
    return {"files": [p.name for p in files], "leaves": total_leaves, "chars": total_chars}


print("############ 第十章（S10xx / 10D / E10…）")
report(EN / "StoryData", "英文基线", r"^EN_(S1[0-9]{3}|10D|E10|ES10)")
present = {p.name for p in (ZH / "StoryData").rglob("*.json")}
en10 = sorted(p.name.replace("EN_", "") for p in (EN / "StoryData").rglob("*.json")
              if re.match(r"^EN_S1[0-9]{3}", p.name))
print("\n第十章英文文件里，零协已有哪些：")
missing = [n for n in en10 if n not in present]
print(f"  共 {len(en10)} 个，零协缺 {len(missing)} 个 → 缺的：{missing}")

print("\n############ 对照：第九章（S9xx）作为参照")
report(EN / "StoryData", "英文基线（第9章）", r"^EN_S9[0-9]{2}")
report(ZH / "StoryData", "零协（第9章）", r"^S9[0-9]{2}")

print("\n############ 章节名 / 关卡表里有没有第十章")
for p in (EN / "StageChapterText.json", ZH / "StageChapterText.json"):
    data = load(p)
    if not data:
        print(f"  {p}: 读不到")
        continue
    rows = data.get("dataList") or []
    hits = [r for r in rows if isinstance(r, dict) and "10" in str(r.get("id") or "")]
    print(f"  {p.parent.name}/{p.name}: 共 {len(rows)} 条，含 '10' 的 {len(hits)} 条")
    for r in hits[:6]:
        print("    ", json.dumps(r, ensure_ascii=False)[:160])
