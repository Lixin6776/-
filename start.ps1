<#
一键启动：后端(8000) + 前端(5173) + 数据源调试浏览器(9222)
可重复执行：已在跑的部分会跳过。
#>
[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$SkipDataSource
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$logs = Join-Path $root ".local\logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

function Test-PortOpen {
    param([int]$Port)
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $client.Connect("127.0.0.1", $Port)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

function Wait-Port {
    param([int]$Port, [int]$Seconds = 40, [string]$Name = "service")
    for ($i = 0; $i -lt ($Seconds * 2); $i++) {
        if (Test-PortOpen $Port) { return $true }
        Start-Sleep -Milliseconds 500
    }
    Write-Host ("  [警告] " + $Name + " 在 " + $Seconds + " 秒内没起来，看日志：" + $logs) -ForegroundColor Yellow
    return $false
}

function Invoke-Utf8Json {
    # PowerShell 5.1 会因为响应头没写 charset 而按 GBK 解码，中文就乱码；
    # 这里自己按 UTF-8 解一遍。
    param([string]$Uri, [string]$Method = "GET", [int]$TimeoutSec = 60)
    $resp = Invoke-WebRequest -Uri $Uri -Method $Method -UseBasicParsing -TimeoutSec $TimeoutSec
    $bytes = $resp.RawContentStream.ToArray()
    $text = [System.Text.Encoding]::UTF8.GetString($bytes)
    return ($text | ConvertFrom-Json)
}

Write-Host ""
Write-Host "=== 直播运营助手 · 启动 ===" -ForegroundColor Cyan
Write-Host ""

# ---------- 1) backend ----------
$python = Join-Path $root ".worktrees\qianchuan-foundation\backend\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = Join-Path $root "backend\.venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "[×] 找不到后端运行环境（venv）" -ForegroundColor Red
    exit 1
}

if (Test-PortOpen 8000) {
    Write-Host "[=] 后端已在运行 (8000)"
} else {
    Write-Host "[+] 启动后端 (8000) ..."
    $backendArgs = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000")
    Start-Process -FilePath $python -ArgumentList $backendArgs -WorkingDirectory (Join-Path $root "backend") -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs "backend.out.log") -RedirectStandardError (Join-Path $logs "backend.err.log")
    Wait-Port -Port 8000 -Name "后端" | Out-Null
}

# ---------- 2) frontend ----------
if (Test-PortOpen 5173) {
    Write-Host "[=] 前端已在运行 (5173)"
} else {
    Write-Host "[+] 启动前端 (5173) ..."
    $pnpm = (Get-Command pnpm.cmd -ErrorAction SilentlyContinue).Source
    if (-not $pnpm) {
        $pnpm = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd"
    }
    if (-not (Test-Path -LiteralPath $pnpm)) {
        Write-Host "[×] 找不到 pnpm，先装 node/pnpm" -ForegroundColor Red
        exit 1
    }
    $feArgs = @("--dir", (Join-Path $root "frontend"), "dev")
    Start-Process -FilePath $pnpm -ArgumentList $feArgs -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs "frontend.out.log") -RedirectStandardError (Join-Path $logs "frontend.err.log")
    Wait-Port -Port 5173 -Name "前端" | Out-Null
}

# ---------- 3) data source: let the backend handle Chrome/9222 ----------
$base = "http://127.0.0.1:8000"
if ($SkipDataSource) {
    Write-Host "[-] 跳过数据源连接"
} elseif (Test-PortOpen 8000) {
    Write-Host "[+] 检查数据源（9222）..."
    try {
        $conn = Invoke-Utf8Json -Uri ($base + "/api/live-watch/connection/connect?mode=auto") -Method POST -TimeoutSec 90
        if ($conn.connected) {
            if ($conn.needs_login) {
                Write-Host "    [注意] 浏览器已打开，需要你在弹出的窗口里登录一次千川" -ForegroundColor Yellow
            } else {
                Write-Host "    [=] 数据源已连接"
            }
        } else {
            Write-Host ("    [警告] 数据源没连上：" + $conn.message) -ForegroundColor Yellow
        }
    } catch {
        Write-Host "    [警告] 连接数据源失败，打开工具后点「连接数据源」再试。" -ForegroundColor Yellow
    }

    try {
        $st = Invoke-Utf8Json -Uri ($base + "/api/live-watch/status") -TimeoutSec 20
        $state = if ($st.running) { "盯盘中" } else { "未开始" }
        Write-Host ("[i] 盯盘：" + $state + "　直播间：" + $st.room_name + "　连续失败：" + $st.consecutive_failures)
        if ((-not $st.running) -and $st.desired_running) {
            Write-Host "[+] 检测到盯盘断开，正在恢复 ..."
            try { Invoke-RestMethod -Uri ($base + "/api/live-watch/resume") -Method POST -TimeoutSec 180 | Out-Null } catch { }
        }
    } catch { }
}

Write-Host ""
Write-Host "=== 就绪 ===" -ForegroundColor Green
Write-Host "工具地址： http://127.0.0.1:5173"
Write-Host ("日志目录： " + $logs)
Write-Host ""

if (-not $NoBrowser) {
    Start-Process "http://127.0.0.1:5173"
}
