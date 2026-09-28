# -*- mode: python ; coding: utf-8 -*-
# 单文件（默认）或目录版（LIMBUS_ONEDIR=1）。
#
# 剧本结构数据（story_stages.json，约 2 MB）**已内置进 exe**：作为位置索引（只存
#   file/page 等文本位置，不含游戏文本正文），内置到 <exe>/limbus_patcher/data/ 下
#   （frozen 时由 package_data_dir() 返回 sys._MEIPASS/limbus_patcher/data）。
#   同时保留外部覆盖优先：程序先读 <exe>/data/cache/story_stages.json，命中即用，
#   未命中才回落到内置数据，更新剧本数据无需重新打包。stage_enemies.json.bak 这类
#   备份文件依旧排除。
import os
from PyInstaller.utils.hooks import collect_submodules  # noqa: F401

block_cipher = None
ONEDIR = os.environ.get("LIMBUS_ONEDIR") == "1"

_DATA_FILES = [
    "category_rules.json",
    "enemy_map.json",
    "entity_exclude.json",
    "misc_story_kinds.json",
    "scenario_model_names.json",
    "season_map.json",
    "stage_enemies.json",
    "story_rpg_plan.json",
    "story_stages.json",
]

# 目录型内置资源：目标路径必须带目录名（否则 PyInstaller 会把内容平铺进目标目录）
_DIR_DATA_FILES = [
    "portraits",  # 人格/E.G.O 卡面（灰机 wiki 抽取，约 17 MB），外部 data/portraits 覆盖优先
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[(f'limbus_patcher/data/{name}', 'limbus_patcher/data') for name in _DATA_FILES]
          + [(f'limbus_patcher/data/{name}', f'limbus_patcher/data/{name}') for name in _DIR_DATA_FILES],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='边狱巴士汉化文本修改器',
    # 图标与版本信息由 scripts/make_icon.py 生成到 assets/（**不要**放 build/：
    # build/ 是 PyInstaller 的 workpath，而 build.ps1 用了 --clean，会在打包前把它删掉）。
    icon='assets/app.ico' if os.path.exists('assets/app.ico') else None,
    version='assets/version_info.txt' if os.path.exists('assets/version_info.txt') else None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if ONEDIR:
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name='边狱巴士汉化文本修改器',
    )
