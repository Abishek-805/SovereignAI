$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.app-venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Project environment missing.' }
if (Get-NetTCPConnection -LocalPort 8088 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 8088 is already in use.' }
$process = Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','backend.app:create_app','--factory','--host','127.0.0.1','--port','8088','--workers','1','--limit-concurrency','64') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'benchmarks\workbench.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'benchmarks\workbench.stderr.log') -PassThru
$process.Id | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'benchmarks\workbench.pid')
Write-Output 'Workbench API starting at http://127.0.0.1:8088. Open this address to upload documents, ask questions and inspect sources.'

