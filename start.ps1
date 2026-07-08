$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $Root "data\server.pid"
$Port = if ($env:PORT) { $env:PORT } else { "8000" }

if (Test-Path $PidFile) {
    $OldPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($OldPid) {
        $Process = Get-CimInstance Win32_Process -Filter "ProcessId = $OldPid" -ErrorAction SilentlyContinue
        if ($Process -and $Process.CommandLine -like "*app.py*" -and $Process.CommandLine -like "*$Root*") {
            Stop-Process -Id ([int]$OldPid) -Force
        }
    }
}

New-Item -ItemType Directory -Path (Join-Path $Root "data") -Force | Out-Null
$AppPath = Join-Path $Root "app.py"
$Process = Start-Process -FilePath "python" -ArgumentList "`"$AppPath`"" -WorkingDirectory $Root -PassThru -WindowStyle Hidden
$Process.Id | Set-Content $PidFile

Write-Host "王者荣耀智能客服机器人已启动：http://127.0.0.1:$Port"
