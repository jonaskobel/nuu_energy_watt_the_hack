param([int]$Port = 8012, [switch]$Restart)
$ErrorActionPreference = 'Stop'
$projectPath = $PSScriptRoot
$runtimePath = Join-Path $projectPath '.runtime'
$statePath = Join-Path $runtimePath 'public-demo.json'
New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Invalid port.' }

# Locate real Python installations, including standard PATH installs on other PCs.
$pythonCandidates = @(
    (Join-Path $projectPath '.venv\Scripts\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
    (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
)
foreach ($name in @('python','python3','py')) {
    $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command -and $command.Source -notlike '*\WindowsApps\*') { $pythonCandidates += $command.Source }
}
$pythonPath = $null
foreach ($candidate in ($pythonCandidates | Select-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $candidate)) { continue }
    try {
        $resolved = & $candidate -c 'import sys; assert sys.version_info >= (3,9); print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath ([string]$resolved))) { $pythonPath=[string]$resolved; break }
    } catch { continue }
}
if (-not $pythonPath) { throw 'Python 3.9+ not found. Install Python or create a .venv in this project.' }

function Record-Process($process, $executable) {
    @{ id=$process.Id; startTicks=$process.StartTime.ToUniversalTime().Ticks.ToString(); executable=$executable }
}
function Get-OwnedProcess($entry) {
    if (-not $entry) { return $null }
    $process = Get-Process -Id $entry.id -ErrorAction SilentlyContinue
    if ($process -and $process.StartTime.ToUniversalTime().Ticks.ToString() -eq $entry.startTicks -and $process.Path -eq $entry.executable) { return $process }
    return $null
}
function Start-DemoWebServer([string]$Origin, [int]$ListenPort) {
    $arguments=@('-B','-m','heat_pump_ready','--runner','disabled','--port',"$ListenPort",'--public-origin',$Origin)
    $server=Start-Process -FilePath $pythonPath -ArgumentList $arguments -WorkingDirectory $projectPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimePath 'server-output.log') -RedirectStandardError (Join-Path $runtimePath 'server-error.log') -PassThru
    try {
        for ($attempt=0; $attempt -lt 30; $attempt++) {
            if ($server.HasExited) { throw 'Website stopped. See .runtime/server-error.log.' }
            try {
                $health=Invoke-RestMethod -Uri "http://127.0.0.1:$ListenPort/api/health" -TimeoutSec 2
                if ($health.status -eq 'ready') { return (Record-Process $server $pythonPath) }
            } catch { Start-Sleep -Milliseconds 500 }
        }
        throw 'Website did not become ready. See .runtime/server-error.log.'
    } catch {
        if (-not $server.HasExited) { Stop-Process -Id $server.Id }
        throw
    }
}

if (Test-Path -LiteralPath $statePath) {
    $saved=Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $tunnelEntry=$saved.processes | Where-Object {$_.executable -like '*cloudflared.exe'} | Select-Object -First 1
    $serverEntry=$saved.processes | Where-Object {$_.executable -like '*python.exe'} | Select-Object -First 1
    $tunnel=Get-OwnedProcess $tunnelEntry
    $server=Get-OwnedProcess $serverEntry
    if ($tunnel -and ($server -or $Restart)) {
        if ($Restart) {
            if ($server) { Stop-Process -Id $server.Id; $server.WaitForExit(5000) | Out-Null }
            $newServer=Start-DemoWebServer $saved.url $saved.port
            $saved.processes=@($tunnelEntry,$newServer)
            $saved | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statePath -Encoding UTF8
        }
        Write-Output $saved.url
        Write-Output 'Demo running. Use -Restart after a git pull to reload the website without changing its public URL.'
        return
    }
    & (Join-Path $projectPath 'Stop-PublicDemo.ps1')
}

$listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
try { $listener.Start() } finally { $listener.Stop() }
$cloudflared=Join-Path $runtimePath 'cloudflared.exe'
if (-not (Test-Path -LiteralPath $cloudflared)) {
    Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile $cloudflared -UseBasicParsing
}
$processes=@()
$tunnelLog=Join-Path $runtimePath 'tunnel-error.log'
try {
    $tunnel=Start-Process -FilePath $cloudflared -ArgumentList @('tunnel','--no-autoupdate','--protocol','http2','--url',"http://127.0.0.1:$Port") -WorkingDirectory $projectPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimePath 'tunnel-output.log') -RedirectStandardError $tunnelLog -PassThru
    $processes += Record-Process $tunnel $cloudflared
    $deadline=[DateTime]::UtcNow.AddSeconds(60)
    $publicUrl=$null
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($tunnel.HasExited) { throw "Tunnel stopped. See $tunnelLog" }
        if (Test-Path -LiteralPath $tunnelLog) {
            $text=Get-Content -LiteralPath $tunnelLog -Raw
            if ($text -match 'https://[a-z0-9-]+\.trycloudflare\.com') { $publicUrl=$Matches[0]; break }
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $publicUrl) { throw "No public URL received. See $tunnelLog" }
    $processes += Start-DemoWebServer $publicUrl $Port
    @{url=$publicUrl; port=$Port; created=[DateTime]::UtcNow.ToString('o'); processes=$processes} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statePath -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $runtimePath 'public-url.txt') -Value $publicUrl -Encoding UTF8
    Write-Output $publicUrl
    Write-Output 'Demo running. Stop with .\Stop-PublicDemo.ps1. Keep this laptop online.'
} catch {
    foreach ($entry in $processes) {
        $process=Get-OwnedProcess $entry
        if ($process) { Stop-Process -Id $process.Id }
    }
    throw
}
