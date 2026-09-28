"""核对发布包：zip 完整性、内容清单、包内 exe 与构建产物是否同一个。"""
from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REL = ROOT / "dist" / "release"
OUT = ROOT / ".workbuddy" / "release_check.txt"
APP = "边狱巴士汉化文本修改器.exe"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    lines: list[str] = []
    build_exe = ROOT / "dist_build" / APP
    lines.append(f"构建产物 exe: {sha256(build_exe)}  ({build_exe.stat().st_size} B)")
    lines.append("")

    for tag in ("portable", "onedir"):
        z = REL / f"LimbusPatcher-v0.9.1-{tag}.zip"
        lines.append(f"=== {z.name}  {z.stat().st_size / 1048576:.1f} MB ===")
        with zipfile.ZipFile(z) as zf:
            bad = zf.testzip()
            lines.append(f"  zip 完整性: {'OK' if bad is None else '损坏 ' + str(bad)}")
            names = zf.namelist()
            lines.append(f"  条目数: {len(names)}")
            top = sorted({n.split('/')[1] for n in names if n.count('/') >= 1 and n.split('/')[1]})
            lines.append(f"  包根目录内容: {top[:8]}")
            exe_entries = [n for n in names if n.endswith(APP)]
            for e in exe_entries:
                data = zf.read(e)
                h = hashlib.sha256(data).hexdigest()
                same = "一致" if h == sha256(build_exe) else "不一致!"
                lines.append(f"  {e}\n    大小 {len(data)} B  sha256 {h}  → 与构建产物 {same}")
            for extra in ("使用说明.txt", "README.md", "LICENSE", "THIRD_PARTY_LICENSES.md"):
                hit = [n for n in names if n.endswith("/" + extra)]
                lines.append(f"  {extra}: {'有' if hit else '缺'}")
            story = [n for n in names if n.endswith("story_stages.json")]
            lines.append(f"  story_stages.json: {'有' if story else '缺'}")
        lines.append("")

    sums = REL / "SHA256SUMS.txt"
    lines.append("=== SHA256SUMS.txt ===")
    lines.append(sums.read_text(encoding="utf-8").strip())

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
