# -*- mode: python ; coding: utf-8 -*-
# 单文件（默认）或目录版（LIMBUS_ONEDIR=1）。
#
# ⚠ 剧本结构数据（story_stages.json，约 2 MB）**不打进 exe**：它随发布包放在
#   <exe>/data/cache/ 下（程序优先读这个位置），这样更新剧本数据不用重新打包，
#   也避免把第三方内容打进二进制。stage_enemies.json.bak 这类备份文件同样排除。
import os
from PyInstaller.utils.hooks import collect_submodules  # noqa: F401

block_cipher = None
ONEDIR = os.environ.get("LIMBUS_ONEDIR") == "1"

_DATA_FILES = [
    "category_rules.json",
    "enemy_map.json",
    "entity_exclude.json",
    "misc_story_kinds.json",
    "season_map.json",
    "stage_enemies.json",
    "story_rpg_plan.json",
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[(f'limbus_patcher/data/{name}', 'limbus_patcher/data') for name in _DATA_FILES],
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
    icon='build/app.ico' if os.path.exists('build/app.ico') else None,
    version='build/version_info.txt' if os.path.exists('build/version_info.txt') else None,
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
