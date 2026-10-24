$ErrorActionPreference = 'Stop'
$runtimePath = Join-Path $PSScriptRoot '.runtime'
$statePath = Join-Path $runtimePath 'public-demo.json'
if (-not (Test-Path -LiteralPath $statePath)) { Write-Output 'No saved demo processes.'; return }
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
foreach ($entry in $state.processes) {
    $p = Get-Process -Id $entry.id -ErrorAction SilentlyContinue
    if ($p -and $p.StartTime.ToUniversalTime().Ticks.ToString() -eq $entry.startTicks -and $p.Path -eq $entry.executable) {
        Stop-Process -Id $p.Id
    }
}
$state | Add-Member -NotePropertyName stopped -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
$state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statePath -Encoding UTF8
Write-Output 'Public demo stopped. The previous public link is no longer served by this laptop.'
