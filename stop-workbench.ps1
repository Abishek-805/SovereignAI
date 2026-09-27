$ErrorActionPreference = 'Stop'
$pidFile = Join-Path $PSScriptRoot 'benchmarks\workbench.pid'
. (Join-Path $PSScriptRoot 'scripts\workbench-process.ps1')
$workbench = Get-SovereignWorkbenchProcess -ProjectRoot $PSScriptRoot
if ($workbench) {
    Stop-SovereignWorkbenchProcess -Workbench $workbench
    Write-Output 'Workbench API stopped.'
} else { Write-Output 'No SovereignAI workbench process is running; any other process on 8088 was left untouched.' }
Remove-Item -LiteralPath $pidFile -ErrorAction SilentlyContinue
