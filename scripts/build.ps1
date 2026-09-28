# 一键构建脚本：依赖安装 → 图标/版本资源 → 测试 → 单文件 + 目录版打包 → 组装发布包
$ErrorActionPreference = "Stop"
# 切到仓库根目录（脚本位于 scripts/ 下，venv / spec / dist 都在根目录）
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "[1/6] 准备虚拟环境"
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
.\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -q pillow

Write-Host "[2/6] 生成图标与版本信息资源（assets/）"
# 必须早于 PyInstaller：--clean 会删掉 build/，所以资源放 assets/（版本库内，可复现）。
.\.venv\Scripts\python.exe scripts\make_icon.py
if ($LASTEXITCODE -ne 0) { throw "图标/版本资源生成失败" }

Write-Host "[3/6] 运行测试"
# 免模态：tests/test_headless_guard.py、test_replace.py 里的对话框流程测试会真的 exec() 模态框，
# 不设这个变量就会在命令行里永久阻塞（不是测试失败，是卡住）。
$env:DSH_NO_MODAL = "1"
# 用一次性 basetemp：默认落在 %TEMP%\pytest-of-<user> 下会跨次累积，
# 收尾清理时容易撞上「批量删除」保护（在受限环境里表现为 pytest 非零退出，
# 看起来像测试失败，其实是清理临时目录被拦）。放一个临时目录里跑完即弃。
$pytestBase = Join-Path $env:TEMP ("limbus-pytest-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
.\.venv\Scripts\python.exe -m pytest tests -q --basetemp=$pytestBase
# pytest 会话结束会自己清掉 basetemp；这里只判退出码。
if ($LASTEXITCODE -ne 0) { throw "测试未通过，终止打包" }

Write-Host "[4/6] PyInstaller 单文件打包"
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean --distpath dist_build limbus_patcher.spec
if ($LASTEXITCODE -ne 0) { throw "单文件版打包失败" }

Write-Host "[5/6] PyInstaller 目录版打包（首启更快、杀软误报更少）"
$env:LIMBUS_ONEDIR = "1"
.\.venv\Scripts\pyinstaller.exe --noconfirm --clean --distpath dist_build limbus_patcher.spec
if ($LASTEXITCODE -ne 0) { throw "目录版打包失败" }
Remove-Item Env:\LIMBUS_ONEDIR

Write-Host "[6/6] 组装发布包"
.\.venv\Scripts\python.exe scripts\make_release.py --dist dist_build
if ($LASTEXITCODE -ne 0) { throw "组装发布包失败" }

Get-ChildItem "dist\release" -Filter *.zip | ForEach-Object {
    Write-Host "产物: $($_.FullName) ($([math]::Round($_.Length/1MB, 1)) MB)"
}
Write-Host "SHA256 见 dist\release\SHA256SUMS.txt"
Write-Host "使用：解压到任意可写目录后双击 exe；data/ 自动生成在 exe 旁。"
