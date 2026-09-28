# -*- coding: utf-8 -*-
"""验证 exe 内部真的含某段 Python 代码（不只是数据文件）。

单文件 exe 的模块被打进 PYZ 归档，磁盘上看不到。本脚本用 PyInstaller 的
归档读取器解出 PYZ，再对指定模块做符号检查，用来回答「我改的代码到底有没有进包」。

用法：
    .venv/Scripts/python.exe scripts/verify_exe_code.py
    .venv/Scripts/python.exe scripts/verify_exe_code.py --exe dist/xxx.exe
    .venv/Scripts/python.exe scripts/verify_exe_code.py --module limbus_patcher.textsource \
        --symbols speaker_of,model_name_of

默认检查 limbus_patcher.textsource —— 它是「全是旁白」修复的关键模块。
退出码：0=通过，1=失败。
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(r"D:\Desktop\lbc")

# 默认：这些模块里只要有任意一个含全部默认符号，且 reports 通过，即算通过
DEFAULT_MODULE = "limbus_patcher.textsource"
DEFAULT_SYMBOLS = [
    "speaker_of",
    "model_name_of",
    "set_game_dirs",
    "load_model_names",
    "global_model_names",
    "CODES_FILE",
    "OVERRIDE_NAME",
]
# 这些模块只需要「调用了 speaker_of」（它们从 textsource 导入）
DEPENDS_ON_SPEAKER = [
    "limbus_patcher.codex",
    "limbus_patcher.storybook",
    "limbus_patcher.ui.main_window",
]


def find_exe(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = ROOT / explicit
        if not p.is_file():
            raise SystemExit(f"exe 不存在：{p}")
        return p
    cand = ROOT / "dist" / "边狱巴士汉化文本修改器.exe"
    if cand.is_file():
        return cand
    # 退而求其次：temp 下最新的构建
    pool = []
    for d in (ROOT / "temp").glob("pyi_dist*"):
        pool += [f for f in d.glob("*.exe")]
    if not pool:
        raise SystemExit("未找到 exe，请用 --exe 指定")
    return max(pool, key=lambda f: f.stat().st_mtime)


def module_symbols(code) -> set[str]:
    """收集模块顶层 co_names + co_consts 里的字符串（含常量名）。"""
    names = set(code.co_names)
    for c in code.co_consts:
        if isinstance(c, str):
            names.add(c)
    return names


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--module", default=DEFAULT_MODULE)
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    args = ap.parse_args()

    exe = find_exe(args.exe)
    want = [s for s in args.symbols.split(",") if s]
    print(f"exe      : {exe}")
    print(f"模块      : {args.module}")
    print(f"需含符号  : {want}")

    try:
        from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader
    except ImportError:
        raise SystemExit("需要 PyInstaller：.venv/Scripts/python.exe -m pip install pyinstaller")

    carch = CArchiveReader(str(exe))
    toc = getattr(carch, "toc", {})
    pyz_name = next((n for n in toc if "PYZ" in n or n.endswith(".pyz")), None)
    if not pyz_name:
        print("FAIL: exe 里找不到 PYZ 归档")
        return 1
    print(f"PYZ 条目  : {pyz_name}")

    pyz_bytes = carch.extract(pyz_name)
    if not pyz_bytes:
        print("FAIL: PYZ 提取为空")
        return 1

    with tempfile.TemporaryDirectory() as td:
        tmp_pyz = Path(td) / "out.pyz"
        tmp_pyz.write_bytes(pyz_bytes)
        zarch = ZlibArchiveReader(str(tmp_pyz))
        mods = set(zarch.toc.keys())

        if args.module not in mods:
            print(f"FAIL: PYZ 内没有模块 {args.module}")
            print("  现有 limbus_patcher.* 模块：",
                  sorted(m for m in mods if m.startswith("limbus_patcher")))
            return 1

        have = module_symbols(zarch.extract(args.module))
        missing = [s for s in want if s not in have]
        hit = [s for s in want if s in have]
        print(f"命中      : {hit}")

        ok = not missing
        # 依赖模块检查（只做提示，不参与通过判定）
        for dep in DEPENDS_ON_SPEAKER:
            if dep in mods:
                dnames = module_symbols(zarch.extract(dep))
                mark = "OK " if "speaker_of" in dnames else "!! "
                print(f"  {mark}{dep} 调用 speaker_of: {'speaker_of' in dnames}")
            else:
                print(f"  ?? {dep} 不在包里")

        if missing:
            print(f"\nFAIL: 缺少符号 {missing} —— 这段代码没进包，需重新构建")
            return 1
        print("\nPASS: 目标模块含全部所需符号，修复代码已在 exe 内")
        return 0


if __name__ == "__main__":
    sys.exit(main())
