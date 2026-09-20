"""把任务文本交给桌面版豆包：复制到剪贴板 + 打开豆包 + 在资源管理器里选中文件。

豆包桌面版注册了 doubao:// 协议（注册表 HKCR\\doubao 已验证），所以：
  1) 文本写进剪贴板（PowerShell Set-Clipboard，UTF-8）
  2) 可选：在资源管理器里选中文件（方便直接拖进豆包）
  3) 可选：唤起豆包窗口

用法：
    python scripts/send_to_doubao.py --file data/misc_story/paste/02_2D.txt
    python scripts/send_to_doubao.py --file x.txt --no-open      # 只复制，不开窗口
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOUBAO_EXE = Path.home() / "AppData/Local/Doubao/Application/app/Doubao.exe"


def to_clipboard(text: str) -> bool:
    """走 PowerShell Set-Clipboard（UTF-8 安全）。"""
    ps = "[Console]::InputEncoding=[Text.Encoding]::UTF8; $input | Set-Clipboard"
    try:
        proc = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                              input=text.encode("utf-8"), capture_output=True, timeout=30)
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def open_doubao() -> bool:
    for cmd in (["cmd", "/c", "start", "", "doubao://"], [str(DOUBAO_EXE)]):
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except OSError:
            continue
    return False


def reveal(path: Path) -> bool:
    try:
        subprocess.Popen(["explorer", "/select,", str(path)])
        return True
    except OSError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=Path, required=True)
    ap.add_argument("--no-open", action="store_true", help="只复制到剪贴板，不打开豆包")
    ap.add_argument("--no-reveal", action="store_true", help="不在资源管理器里选中文件")
    args = ap.parse_args()
    path: Path = args.file
    if not path.is_file():
        print(f"文件不存在：{path}")
        return 2
    text = path.read_text(encoding="utf-8")
    ok = to_clipboard(text)
    print(f"{'已复制' if ok else '复制失败'}：{path.name}（{len(text)} 字符）")
    if not args.no_reveal:
        reveal(path)
    if not args.no_open:
        open_doubao()
    if ok:
        print("现在到豆包窗口按 Ctrl+V 粘贴，回车发送即可。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
