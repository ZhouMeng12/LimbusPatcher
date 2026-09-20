"""组装发布包：onefile / onedir 两个 zip + SHA256 清单。

    python scripts/build.ps1                 # 先构建（跑测试 → onefile → onedir）
    python scripts/make_release.py           # 再组装 dist/release/*.zip

发布包内容（**只含程序与结构数据**，不含游戏 / 零协文本、不含索引、不含你的方案）：
  · 边狱巴士汉化文本修改器.exe（或 onedir 目录）
  · data/cache/story_stages.json       剧本结构（只有「位置」，文本运行时从游戏语言文件取）
  · README.md / LICENSE / THIRD_PARTY_LICENSES.md / 使用说明.txt
  · SHA256SUMS.txt
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from limbus_patcher import APP_NAME, __version__  # noqa: E402

DIST = ROOT / "dist_build"   # 构建产物目录（与 dist/ 解耦：程序开着占用 dist 里的 exe 也能打包）
RELEASE = ROOT / "dist" / "release"
STORY = ROOT / "limbus_patcher" / "data" / "story_stages.json"
DOCS = ("README.md", "LICENSE", "THIRD_PARTY_LICENSES.md")

USAGE = """{app} v{version}（公测）

怎么用
  1) 解压到**任意可写目录**（不要放 Program Files），双击 exe。
  2) 首次启动会自动扫描 Steam 库找游戏目录；找不到就手动选（含 LimbusCompany.exe 的那层）。
  3) 等文本索引建好（一次性；弹窗结束会自动关闭）。
  4) 左边浏览 / 顶部搜索 → 选中条目 → 右侧输入自定义文本 → Ctrl+S 保存。
  5) 点「应用到游戏」→ 进游戏，标题画面左下角语言按钮选 LLC_zh-CN_custom（首次一次即可）。
  6) 想还原：程序里「操作 ▾ → 还原为零协原包」，或删掉 Lang/LLC_zh-CN_custom 目录。

没装零协汉化？
  程序会自动改用游戏自带的**英文原文**作为文本来源：浏览 / 搜索 / 对照 / 翻译都能用，
  但「应用到游戏」需要零协汉化（副本语言包是从零协包镜像出来的）。
  一键安装：https://www.zeroasso.top/docs/install/autoinstall

注意
  · 本工具与 Project Moon、零协会汉化组均无隶属关系，仅供个人汉化对照使用。
  · 不会修改零协原始汉化与游戏英文基线，只写独立的副本语言包；改前自动备份。
  · 发布包内不含任何游戏素材与第三方译文；剧本数据只存「位置」，文本读你本机的语言文件。
"""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stage(target: Path, payload: Path, onefile: bool) -> None:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    if payload.is_dir():
        shutil.copytree(payload, target / payload.name)
    else:
        shutil.copy2(payload, target / payload.name)
    cache = target / "data" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STORY, cache / "story_stages.json")
    for name in DOCS:
        src = ROOT / name
        if src.is_file():
            shutil.copy2(src, target / name)
    (target / "使用说明.txt").write_text(
        USAGE.format(app=APP_NAME, version=__version__), encoding="utf-8", newline="\r\n")
    print(f"  暂存 {target.name}（{sum(f.stat().st_size for f in target.rglob('*') if f.is_file()) / 1048576:.1f} MB）")


def zip_dir(src: Path, out: Path) -> None:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in sorted(src.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(src.parent))
    print(f"  {out.name}  {out.stat().st_size / 1048576:.1f} MB")


def main() -> int:
    ap = argparse.ArgumentParser(description="组装发布包")
    ap.add_argument("--skip-missing", action="store_true", help="缺哪个产物就跳过，不报错")
    ap.add_argument("--dist", default=None, help="构建产物目录（默认 dist_build）")
    args = ap.parse_args()
    dist = Path(args.dist) if args.dist else DIST

    RELEASE.mkdir(parents=True, exist_ok=True)
    exe = dist / f"{APP_NAME}.exe"
    onedir = dist / APP_NAME
    built: list[tuple[str, Path, bool]] = []
    if exe.is_file():
        built.append(("portable", exe, True))
    if onedir.is_dir():
        built.append(("onedir", onedir, False))
    if not built:
        print(f"{dist} 下没有找到构建产物，先跑 scripts/build.ps1")
        return 1
    if not STORY.is_file():
        print(f"缺少剧本结构数据 {STORY}（先跑 scripts/build_story_rpg.py）")
        return 1

    sums: list[str] = []
    for tag, payload, onefile in built:
        # 包名用 ASCII：GitHub Release 会把附件名里的非 ASCII 字符吃掉（中文前缀直接被删）
        name = f"LimbusPatcher-v{__version__}-{tag}"
        staging = RELEASE / name
        stage(staging, payload, onefile)
        out = RELEASE / f"{name}.zip"
        zip_dir(staging, out)
        sums.append(f"{sha256(out)}  {out.name}")
        shutil.rmtree(staging)

    (RELEASE / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\r\n")
    print("\n".join(sums))
    print(f"\n发布包目录：{RELEASE}")
    if not built and not args.skip_missing:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
