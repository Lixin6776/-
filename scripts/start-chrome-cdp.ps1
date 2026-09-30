$chromeCandidates = @(
  "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
  "${env:LOCALAPPDATA}\Google\Chrome\Application\chrome.exe"
)
$chrome = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $chrome) { throw "Chrome executable not found." }

$profile = Join-Path $env:LOCALAPPDATA "QianchuanAssistantChrome"
New-Item -ItemType Directory -Force -Path $profile | Out-Null

Write-Output "Starting Qianchuan browser on 127.0.0.1:9222. Keep this terminal open until you close Chrome."
& $chrome `
  "--remote-debugging-address=127.0.0.1" `
  "--remote-debugging-port=9222" `
  "--user-data-dir=$profile" `
  "https://qianchuan.jinritemai.com/"