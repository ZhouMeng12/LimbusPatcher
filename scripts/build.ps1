# 一键构建脚本：依赖安装 → 测试 → 单文件 + 目录版打包 → 组装发布包
$ErrorActionPreference = "Stop"
# 切到仓库根目录（脚本位于 scripts/ 下，venv / spec / dist 都在根目录）
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "[1/5] 准备虚拟环境"
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
.\.venv\Scripts\python.exe -m pip install -q -r requirements.txt

Write-Host "[2/5] 运行测试"
# 免模态：tests/test_headless_guard.py、test_replace.py 里的对话框流程测试会真的 exec() 模态框，
# 不设这个变量就会在命令行里永久阻塞（不是测试失败，是卡住）。
$env:DSH_NO_MODAL = "1"
.\.venv\Scripts\python.exe -m pytest tests -q
if ($LASTEXITCODE -ne 0) { throw "测试未通过，终止打包" }

Write-Host "[3/5] PyInstaller 单文件打包"
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean --distpath dist_build limbus_patcher.spec
if ($LASTEXITCODE -ne 0) { throw "单文件版打包失败" }

Write-Host "[4/5] PyInstaller 目录版打包（首启更快、杀软误报更少）"
$env:LIMBUS_ONEDIR = "1"
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean --distpath dist_build limbus_patcher.spec
if ($LASTEXITCODE -ne 0) { throw "目录版打包失败" }
Remove-Item Env:\LIMBUS_ONEDIR

Write-Host "[5/5] 组装发布包"
.\.venv\Scripts\python.exe scripts\make_release.py --dist dist_build
if ($LASTEXITCODE -ne 0) { throw "组装发布包失败" }

Get-ChildItem "dist\release" -Filter *.zip | ForEach-Object {
    Write-Host "产物: $($_.FullName) ($([math]::Round($_.Length/1MB, 1)) MB)"
}
Write-Host "SHA256 见 dist\release\SHA256SUMS.txt"
Write-Host "使用：解压到任意可写目录后双击 exe；data/ 自动生成在 exe 旁。"
