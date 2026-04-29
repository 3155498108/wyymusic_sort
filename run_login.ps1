$node = "C:\Program Files\nodejs\node.exe"
$ncm = "C:\Users\spenc\AppData\Roaming\npm\node_modules\@music163\ncm-cli\dist\index.js"
$outFile = "$env:TEMP\ncm_login_test.txt"
$errFile = "$env:TEMP\ncm_login_err.txt"

Write-Host "Starting ncm-cli login..."
$proc = Start-Process -FilePath $node -ArgumentList $ncm,"login","--background","--output","json" -PassThru -NoNewWindow -RedirectStandardOutput $outFile -RedirectStandardError $errFile

Start-Sleep 5

if (Test-Path $outFile) {
    $content = Get-Content $outFile -Raw
    Write-Host "Output: $content"
}

if ($proc -and -not $proc.HasExited) {
    Stop-Process $proc.Id -Force -ErrorAction SilentlyContinue
}
Remove-Item $outFile -Force -ErrorAction SilentlyContinue
Remove-Item $errFile -Force -ErrorAction SilentlyContinue