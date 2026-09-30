$root = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $root ".local\logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

$python = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
  throw "Backend virtual environment not found. Run the backend setup first."
}

$pnpm = (Get-Command pnpm.cmd -ErrorAction SilentlyContinue).Source
if (-not $pnpm) {
  $pnpm = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd"
}
if (-not (Test-Path -LiteralPath $pnpm)) {
  throw "pnpm was not found."
}

Start-Process -FilePath $python `
  -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") `
  -WorkingDirectory (Join-Path $root "backend") `
  -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $logs "backend.out.log") `
  -RedirectStandardError (Join-Path $logs "backend.err.log")

Start-Process -FilePath $pnpm `
  -ArgumentList @("--dir", (Join-Path $root "frontend"), "dev") `
  -WorkingDirectory $root `
  -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $logs "frontend.out.log") `
  -RedirectStandardError (Join-Path $logs "frontend.err.log")

Write-Output "Backend: http://127.0.0.1:8000"
Write-Output "Frontend: http://127.0.0.1:5173"
Write-Output "Logs: $logs"