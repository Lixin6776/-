$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Backend virtual environment not found." }
$output = Join-Path $root ".local\selector-probe"
New-Item -ItemType Directory -Force -Path $output | Out-Null
$code = "import asyncio; from pathlib import Path; from app.execution.cdp.page_probe import PageProbe; asyncio.run(PageProbe('http://127.0.0.1:9222').capture('qianchuan', Path(r'$output')))"
Set-Location (Join-Path $root "backend")
& $python -c $code
Write-Output "Captured page.html and page.png in $output"
Write-Output "Fill .local/selectors/qianchuan.json with the required selector keys from SelectorConfig."