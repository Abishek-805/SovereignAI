$ErrorActionPreference = 'Stop'
$pidFile = Join-Path $PSScriptRoot 'benchmarks\server.pid'
$expectedPath = Join-Path $PSScriptRoot 'runtime\llama-b11132\llama-server.exe'
$ownedModelRoot = Join-Path $PSScriptRoot 'models\'
$serverProcessId = if (Test-Path -LiteralPath $pidFile) { [int](Get-Content -LiteralPath $pidFile) } else { 0 }
$serverProcess = if ($serverProcessId) { Get-CimInstance Win32_Process -Filter "ProcessId=$serverProcessId" -ErrorAction SilentlyContinue } else { $null }
if ($serverProcess -and $serverProcess.ExecutablePath -eq $expectedPath -and
    $serverProcess.CommandLine.Contains($ownedModelRoot) -and $serverProcess.CommandLine.Contains('--port 8087')) {
    Stop-Process -Id $serverProcessId
    if (Test-Path -LiteralPath $pidFile) { Remove-Item -LiteralPath $pidFile }
    Write-Output 'Local model stopped.'
} else {
    Write-Output 'No saved SovereignAI model process is running; any other process on 8087 was left untouched.'
}
