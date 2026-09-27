$ErrorActionPreference = 'Stop'
$pidFile = Join-Path $PSScriptRoot 'benchmarks\workbench.pid'
$expectedPython = Join-Path $PSScriptRoot '.app-venv\Scripts\python.exe'
$processId = if (Test-Path -LiteralPath $pidFile) { [int](Get-Content -LiteralPath $pidFile) } else { 0 }
$processInfo = if ($processId) { Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue } else { $null }
if ($processInfo -and $processInfo.ExecutablePath -eq $expectedPython -and $processInfo.CommandLine -like '*backend.app:create_app*') {
    # CPython venv launchers may own a child interpreter. Stop only this recorded process tree.
    Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $processId -and $_.CommandLine -like '*backend.app:create_app*' } | ForEach-Object { Stop-Process -Id $_.ProcessId }
    Stop-Process -Id $processId -ErrorAction SilentlyContinue
    Write-Output 'Workbench API stopped.'
} else { Write-Output 'No saved SovereignAI workbench process is running; any other process on 8088 was left untouched.' }
