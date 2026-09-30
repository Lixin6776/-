param(
  [string]$ProfilePath = "",
  [int]$Port = 9222
)

$chromeCandidates = @(
  "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
  "${env:LOCALAPPDATA}\Google\Chrome\Application\chrome.exe"
)
$chrome = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $chrome) { throw "Chrome executable not found." }

if (-not $ProfilePath) {
  $ProfilePath = Join-Path $env:LOCALAPPDATA "QianchuanAssistantChrome"
}
$profile = $ProfilePath
New-Item -ItemType Directory -Force -Path $profile | Out-Null

Write-Output "Starting Qianchuan browser on 127.0.0.1:$Port. Keep this terminal open until you close Chrome."
& $chrome `
  "--remote-debugging-address=127.0.0.1" `
  "--remote-debugging-port=$Port" `
  "--remote-allow-origins=*" `
  "--restore-last-session" `
  "--no-first-run" `
  "--user-data-dir=$profile" `
  "https://qianchuan.jinritemai.com/"