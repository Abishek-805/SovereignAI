param(
    [ValidateRange(1, 86400)]
    [int]$IdleSeconds = 60
)

$ErrorActionPreference = 'Stop'
$runtimePath = Join-Path $PSScriptRoot 'runtime\llama-b11132\llama-server.exe'
$modelPath = Join-Path $PSScriptRoot 'models\Qwen3-4B-Instruct-2507-Q4_K_M.gguf'
$logDirectory = Join-Path $PSScriptRoot 'benchmarks'
if (!(Test-Path -LiteralPath $runtimePath) -or !(Test-Path -LiteralPath $modelPath)) {
    throw 'Runtime or model is missing. Finish the setup download first.'
}
if (Get-NetTCPConnection -LocalPort 8087 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8087 is already in use. The local model may already be running.'
}
$serverArguments = @('-m', ('"' + $modelPath + '"'), '--alias', 'sovereign-text', '-c', '24576', '--n-predict', '4096', '-np', '1', '-b', '256', '-ub', '128', '-t', '6', '-fa', 'on', '-ctk', 'q8_0', '-ctv', 'q8_0', '--fit', 'on', '--fit-target', '512', '--host', '127.0.0.1', '--port', '8087', '--cors-origins', 'localhost', '--offline', '--sleep-idle-seconds', "$IdleSeconds", '-lv', '4')
$serverProcess = Start-Process -FilePath $runtimePath -ArgumentList $serverArguments -WorkingDirectory (Split-Path $runtimePath) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDirectory 'server.stdout.log') -RedirectStandardError (Join-Path $logDirectory 'server.stderr.log') -PassThru
$serverProcess.Id | Set-Content -LiteralPath (Join-Path $logDirectory 'server.pid')
Write-Output "Local model starting (PID $($serverProcess.Id)). Chat: http://127.0.0.1:8087"
Write-Output "Model unloads after $IdleSeconds idle seconds and reloads on the next request."
