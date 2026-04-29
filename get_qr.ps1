# get_qr.ps1 - 获取 ncm-cli QR 登录 URL
$ErrorActionPreference = "SilentlyContinue"
$node = "C:\Users\spenc\AppData\Roaming\npm\node_modules\@music163\ncm-cli\dist\index.js"
$proc = Start-Process -FilePath "node" -ArgumentList $node,"login","--background","--output","json" -PassThru -NoNewWindow -RedirectStandardOutput "$env:TEMP\ncm_qr_out.txt" -RedirectStandardError "$env:TEMP\ncm_qr_err.txt"
Start-Sleep -Seconds 2
if (Test-Path "$env:TEMP\ncm_qr_out.txt") {
    $content = Get-Content "$env:TEMP\ncm_qr_out.txt" -Raw
    $content
    Remove-Item "$env:TEMP\ncm_qr_out.txt" -Force -ErrorAction SilentlyContinue
}
if ($proc -and -not $proc.HasExited) {
    Stop-Process $proc.Id -Force -ErrorAction SilentlyContinue
}
Remove-Item "$env:TEMP\ncm_qr_err.txt" -Force -ErrorAction SilentlyContinue
