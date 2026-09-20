"""打包版存活探测：启动 exe，逐秒观察是否早退（区分「启动即崩」与「正常运行被杀」）。

用法：python scripts/probe_exe.py [秒数]
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = next(ROOT.glob("dist/*.exe"))
CRASH = ROOT / "dist" / "data" / "crash.log"
WAIT = int(sys.argv[1]) if len(sys.argv) > 1 else 45

before = CRASH.stat().st_mtime if CRASH.exists() else 0
print("exe:", EXE.name, f"({EXE.stat().st_size / 1048576:.1f} MB, "
      f"{time.strftime('%m-%d %H:%M', time.localtime(EXE.stat().st_mtime))})")
proc = subprocess.Popen([str(EXE)], cwd=str(ROOT / "dist"))
died_at = None
for i in range(WAIT):
    time.sleep(1)
    code = proc.poll()
    if code is not None:
        died_at = (i + 1, code)
        break
    if i in (2, 9, 19, 29):
        print(f"  {i + 1}s 仍在运行 ✓")
if died_at:
    print(f"❌ 进程在 {died_at[0]} 秒后退出，返回码 {died_at[1]}（0xC0000005=访问越界，"
          f"0xC0000409=栈溢出/快速失败，负数=被信号终止）")
else:
    print(f"✅ 存活 {WAIT} 秒，正常（随后结束本次探测）")
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, text=True)
time.sleep(1)
if CRASH.exists() and CRASH.stat().st_mtime > before:
    print("—— crash.log（新）——")
    print(CRASH.read_text(encoding="utf-8", errors="replace")[-2500:])
else:
    print("crash.log：无新内容" + ("（文件不存在）" if not CRASH.exists() else ""))
