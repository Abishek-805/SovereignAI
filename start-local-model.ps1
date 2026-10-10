param(
    [ValidateRange(1, 86400)]
    [int]$IdleSeconds = 600
)

$ErrorActionPreference = 'Stop'
$runtimePath = Join-Path $PSScriptRoot 'runtime\llama-b11132\llama-server.exe'
# Use the same installed primary worker and context as the backend registry.
$pythonPath = Join-Path $PSScriptRoot '.app-venv\Scripts\python.exe'
Push-Location $PSScriptRoot
try {
    $modelConfiguration = & $pythonPath -c "import json; from router.model_registry import ModelRegistry; r=ModelRegistry(); print(json.dumps({'args':r.launch_args('text')}))"
    if ($LASTEXITCODE -ne 0) { throw 'Could not read the configured local model registry.' }
    $modelConfiguration = $modelConfiguration | ConvertFrom-Json
} finally { Pop-Location }
$runtimePath = [string]$modelConfiguration.args[0]
$logDirectory = Join-Path $PSScriptRoot 'benchmarks'
if (!(Test-Path -LiteralPath $runtimePath)) {
    throw 'Runtime or model is missing. Finish the setup download first.'
}
if (Get-NetTCPConnection -LocalPort 8087 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8087 is already in use. The local model may already be running.'
}
$serverArguments = @($modelConfiguration.args | Select-Object -Skip 1)
# Start-Process joins ArgumentList on Windows; quote paths containing spaces.
for ($argumentIndex = 0; $argumentIndex -lt $serverArguments.Count; $argumentIndex++) {
    if ($serverArguments[$argumentIndex] -eq '--sleep-idle-seconds') {
        $serverArguments[$argumentIndex + 1] = [string]$IdleSeconds
    }
    if ($serverArguments[$argumentIndex] -match '\s') {
        $serverArguments[$argumentIndex] = '"' + $serverArguments[$argumentIndex] + '"'
    }
}
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$serverProcess = Start-Process -FilePath $runtimePath -ArgumentList $serverArguments -WorkingDirectory (Split-Path $runtimePath) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDirectory 'server.stdout.log') -RedirectStandardError (Join-Path $logDirectory 'server.stderr.log') -PassThru
$serverProcess.Id | Set-Content -LiteralPath (Join-Path $logDirectory 'server.pid')
Write-Output "Local model starting (PID $($serverProcess.Id)). Chat: http://127.0.0.1:8087"
Write-Output "Model unloads after $IdleSeconds idle seconds and reloads on the next request."
