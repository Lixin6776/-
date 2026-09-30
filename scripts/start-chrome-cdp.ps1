$chromeCandidates = @(
  "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
  "${env:LOCALAPPDATA}\Google\Chrome\Application\chrome.exe"
)
$chrome = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $chrome) { throw "Chrome executable not found." }

$profile = Join-Path $env:LOCALAPPDATA "QianchuanAssistantChrome"
New-Item -ItemType Directory -Force -Path $profile | Out-Null

Start-Job -ScriptBlock {
  & $using:chrome "--remote-debugging-address=127.0.0.1" `
    "--remote-debugging-port=9222" `
    "--user-data-dir=$using:profile" `
    "https://qianchuan.jinritemai.com/"
} | Out-Null