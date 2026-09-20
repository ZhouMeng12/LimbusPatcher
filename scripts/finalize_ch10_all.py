"""第十章全套收尾：错译名校正 → 装补译文件 → 出处报告 → 校验。

用法：python scripts/finalize_ch10_all.py [--data-dir data]
产物：
  data/translate/out/第十章-中文剧本.md / 中英对照.md      （剧情）
  data/translate/out/第十章-RPG与数据文本.md               （RPG + 技能/状态/UI 的英中对照）
  <data-dir>/supplement/…                                   （补译文件，供「应用到游戏」）
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
sys.path.insert(0, str(ROOT / "scripts"))
import mt_files as mf  # noqa: E402
import translate_pack as tp  # noqa: E402


def run(script: str, *args: str, tail: int = 6) -> str:
    proc = subprocess.run([PY, str(ROOT / "scripts" / script), *args], cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=600)
    out = (proc.stdout or "").strip()
    lines = out.splitlines()
    print("\n".join(lines[-tail:]), flush=True)
    return out


def build_data_report() -> Path:
    """RPG + 数据文件的英中对照报告。"""
    lines = ["# 第十章 · RPG 与数据文本（英中对照）", "",
             "RPG 模式（第十章新增玩法）与技能/状态/道具/UI 文本。术语已按零协既有译法锁定。", ""]
    for rel in mf.RPG_FILES + mf.CH10_FILES:
        out = mf.OUT / rel
        if not out.is_file():
            continue
        src = mf.en_path(rel)
        try:
            en = json.loads(src.read_text(encoding="utf-8-sig"))
            zh = json.loads(out.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        en_rows = en.get("dataList") if isinstance(en, dict) else en
        zh_rows = zh.get("dataList") if isinstance(zh, dict) else zh
        if not isinstance(en_rows, list) or not isinstance(zh_rows, list):
            continue
        lines += [f"## {rel}", ""]
        for e, z in zip(en_rows, zh_rows):
            if not isinstance(e, dict) or not isinstance(z, dict):
                continue
            for field, en_text in e.items():
                if not isinstance(en_text, str) or not en_text.strip():
                    continue
                zh_text = z.get(field)
                if not isinstance(zh_text, str):
                    continue
                tag = e.get("key") or e.get("id") or ""
                lines.append(f"- `{tag}` **{zh_text.strip()}**")
                lines.append(f"  - {en_text.strip()}")
        lines.append("")
    target = ROOT / "data" / "translate" / "out" / "第十章-RPG与数据文本.md"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = ap.parse_args()

    print("1) 错译名校正（剧情 + RPG/数据文件）", flush=True)
    run("fix_variants.py", tail=3)
    print("2) 剧情合并与报告", flush=True)
    run("finalize_ch10.py", tail=5)
    print("3) 安装补译文件", flush=True)
    run("install_supplement.py", "--data-dir", str(args.data_dir), tail=3)
    print("4) RPG/数据文本对照报告", flush=True)
    target = build_data_report()
    print(f"   {target}  ({target.stat().st_size / 1024:.0f} KB)")

    # 汇总
    missing_story = [n for n in tp.STORY_FILES if not (tp.ZH_DIR / f"{n}.json").is_file()]
    missing_data = [r for r in mf.CH10_FILES + mf.RPG_FILES if not (mf.OUT / r).is_file()]
    print(f"\n剧情文件缺：{missing_story or '无'}")
    print(f"数据/RPG 文件缺：{missing_data or '无'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
