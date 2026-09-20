"""第十章收尾：错译名校正 → 标签补齐 → 全量合并 → 术语校验 → 出成品报告。

用法：python scripts/finalize_ch10.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")


def run(script: str, *args: str) -> None:
    print(f"\n$ {script} {' '.join(args)}".rstrip(), flush=True)
    proc = subprocess.run([PY, str(ROOT / "scripts" / script), *args], cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=300)
    out = (proc.stdout or "").strip()
    print("\n".join(out.splitlines()[-12:]), flush=True)


def main() -> int:
    run("fix_variants.py")
    run("fix_tags.py")
    sys.path.insert(0, str(ROOT / "scripts"))
    import translate_pack as tp  # noqa: E402

    for name in tp.STORY_FILES:
        if (tp.ZH_DIR / f"{name}.json").is_file():
            run("translate_pack.py", "merge", name)
    run("translate_pack.py", "status")
    run("translate_pack.py", "check")
    run("qa_review.py")
    out = ROOT / "data" / "translate" / "out"
    print("\n成品：")
    for p in sorted(out.glob("*.md")):
        print(f"  {p}  ({p.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
