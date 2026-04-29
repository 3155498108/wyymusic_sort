# build_package.ps1 - 构建网易云歌单排序器
# 策略：node.exe + npx/npm.cmd + Python PyQt6 打包应用
# playlist 命令通过系统 npx 调用全局 ncm-cli
$ErrorActionPreference = "Stop"
$BASE = "E:\jsjzy\pyqt_app"
$DIST = "$BASE\dist"

Write-Host "Step 1: Create directories (keep node/npm/npx)"
Remove-Item "$DIST\网易云歌单排序器" -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "$DIST" -Force | Out-Null
Write-Host "OK"

Write-Host "Step 2: Copy Node.js and npm/npx"
Copy-Item "C:\Program Files\nodejs\node.exe" "$DIST\node.exe"
Copy-Item "C:\Program Files\nodejs\npm.cmd" "$DIST\npm.cmd"
Copy-Item "C:\Program Files\nodejs\npx.cmd" "$DIST\npx.cmd"
$nodeSize = [math]::Round((Get-Item "C:\Program Files\nodejs\node.exe").Length / 1MB, 1)
Write-Host "Node.js + npm + npx copied: $nodeSize MB"

Write-Host "Step 3: Build with PyInstaller"
$pyInstaller = Get-Command pyinstaller -ErrorAction SilentlyContinue
if (-not $pyInstaller) {
    Write-Host "Installing PyInstaller..."
    & pip install pyinstaller 2>&1 | Out-Null
}
$APPY = "$BASE\main.py"
Push-Location $BASE
try {
    & pyinstaller --onedir --name "网易云歌单排序器" --distpath $DIST --clean -y $APPY 2>&1 | Out-Null
} catch {
    Write-Host "PyInstaller error: $_"
}
Pop-Location

Write-Host "`nDone! dist: $DIST"
Get-ChildItem $DIST -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum | ForEach-Object {
    $sz = [math]::Round($_.Sum / 1MB, 1)
    Write-Host "Total: $sz MB"
}
