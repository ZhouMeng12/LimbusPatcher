"""把当前状态提交到 git，作为一次「修改备份」。

用法：
    python scripts/git_snapshot.py                # 自动消息（带时间）
    python scripts/git_snapshot.py "改了 W 公司台词"
    python scripts/git_snapshot.py --status       # 只看有没有变化，不提交

说明：
- 代码 + 小体积数据（图鉴图、AI 判定表、剧本对齐数据）走普通提交；
- 用户自己的修改（data/profiles/*.json、data/config.json，以及打包版 dist/data 下同名文件）
  在 .gitignore 里被排除，这里用 ``git add -f`` 强制纳入，所以「备份修改」也能进版本库；
- 没有任何变化时不会产生空提交。
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
#: 需要强制纳入版本库的用户修改（存在才提交）
FORCED = [
    "data/config.json",
    "data/profiles",
    "dist/data/config.json",
    "dist/data/profiles",
]


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def main(argv: list[str]) -> int:
    if git("rev-parse", "--is-inside-work-tree").returncode != 0:
        print("这里还不是 git 仓库：先运行 git init（仓库根：%s）" % ROOT)
        return 1

    status_args = ["--status"] if "--status" in argv else []
    message = " ".join(a for a in argv if not a.startswith("--")).strip()
    message = message or f"备份修改 {datetime.now():%Y-%m-%d %H:%M}"

    git("add", "-A")
    for rel in FORCED:
        path = ROOT / rel
        if path.exists():
            git("add", "-f", rel)
    staged = git("diff", "--cached", "--name-only").stdout.strip()
    if not staged:
        print("没有需要备份的变化（工作区干净）。")
        return 0
    if status_args:
        print(staged)
        return 0

    res = git("commit", "-m", message)
    if res.returncode != 0:
        print("提交失败：", (res.stderr or res.stdout).strip())
        return 1
    files = len([l for l in staged.splitlines() if l.strip()])
    print(f"已备份 {files} 个文件：{message}")
    print(git("log", "--oneline", "-1").stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
