param(
    [ValidateRange(1, 86400)]
    [int]$IdleSeconds = 600
)

$ErrorActionPreference = 'Stop'
$runtimePath = Join-Path $PSScriptRoot 'runtime\llama-b11132\llama-server.exe'
$modelPath = Join-Path $PSScriptRoot 'models\Qwen3-4B-Instruct-2507-Q4_K_M.gguf'
$contextSize = '24576'
$modelAlias = 'sovereign-text'
$upgradedModelPath = Join-Path $PSScriptRoot 'models\gemma-4-E2B-it-Q4_K_M.gguf'
if (Test-Path -LiteralPath $upgradedModelPath) {
    $modelPath = $upgradedModelPath
    $contextSize = '16384'
}
# Match default_specs: the reasoning upgrade moves the previous text worker
# to its lightweight alias. Startup retains that smaller worker.
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'models\Qwen3.5-4B-Q4_K_M.gguf')) {
    $modelAlias = 'sovereign-text-light'
}
$logDirectory = Join-Path $PSScriptRoot 'benchmarks'
if (!(Test-Path -LiteralPath $runtimePath) -or !(Test-Path -LiteralPath $modelPath)) {
    throw 'Runtime or model is missing. Finish the setup download first.'
}
if (Get-NetTCPConnection -LocalPort 8087 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8087 is already in use. The local model may already be running.'
}
$serverArguments = @('-m', ('"' + $modelPath + '"'), '--alias', $modelAlias, '-c', $contextSize, '--n-predict', '8192', '-np', '1', '-b', '256', '-ub', '128', '-t', '6', '-fa', 'on', '-ctk', 'q8_0', '-ctv', 'q8_0', '--fit', 'on', '--fit-target', '1024', '--host', '127.0.0.1', '--port', '8087', '--cors-origins', 'localhost', '--offline', '--sleep-idle-seconds', "$IdleSeconds", '-lv', '4')
$serverProcess = Start-Process -FilePath $runtimePath -ArgumentList $serverArguments -WorkingDirectory (Split-Path $runtimePath) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDirectory 'server.stdout.log') -RedirectStandardError (Join-Path $logDirectory 'server.stderr.log') -PassThru
$serverProcess.Id | Set-Content -LiteralPath (Join-Path $logDirectory 'server.pid')
Write-Output "Local model starting (PID $($serverProcess.Id)). Chat: http://127.0.0.1:8087"
Write-Output "Model unloads after $IdleSeconds idle seconds and reloads on the next request."
