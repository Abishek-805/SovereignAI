param(
    [ValidateRange(1, 86400)]
    [int]$IdleSeconds = 600,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\workbench-process.ps1')
$model = 'http://127.0.0.1:8087'
$app = 'http://127.0.0.1:8088'

# A fresh clone needs only Python 3.12, Node.js and the separately downloaded
# local model/runtime assets. Keep setup behind the single requirements file.
$pythonPath = Join-Path $PSScriptRoot '.app-venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $pythonPath)) {
    & py -3.12 -m venv (Join-Path $PSScriptRoot '.app-venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required. See README.md.' }
    & $pythonPath -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
}
$embeddingManifest = Join-Path $PSScriptRoot 'models\bge-small-en-v1.5\manifest.json'
if (!(Test-Path -LiteralPath $embeddingManifest)) {
    & $pythonPath (Join-Path $PSScriptRoot 'setup-embeddings.py')
    if ($LASTEXITCODE -ne 0) { throw 'Embedding setup failed. See README.md.' }
}
$frontend = Join-Path $PSScriptRoot 'frontend\llama-ui'
if (!(Test-Path -LiteralPath (Join-Path $frontend 'dist\index.html'))) {
    Push-Location $frontend
    try {
        & npm ci
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
}

function Test-LocalHealth([string]$url) {
    try {
        $response = Invoke-WebRequest -Uri "$url/health" -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-OwnedModelListener {
    $pidFile = Join-Path $PSScriptRoot 'benchmarks\server.pid'
    if (!(Test-Path -LiteralPath $pidFile)) { return $false }
    $savedId = [int](Get-Content -LiteralPath $pidFile)
    $listener = Get-NetTCPConnection -LocalPort 8087 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (!$listener -or $listener.OwningProcess -ne $savedId) { return $false }
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$savedId" -ErrorAction SilentlyContinue
    $expectedExe = Join-Path $PSScriptRoot 'runtime\llama-b11132\llama-server.exe'
    $modelRoot = Join-Path $PSScriptRoot 'models\'
    return ($processInfo -and $processInfo.ExecutablePath -eq $expectedExe -and
            $processInfo.CommandLine.Contains($modelRoot) -and $processInfo.CommandLine.Contains('--port 8087'))
}

function Test-OwnedWorkbenchListener {
    return [bool](Get-SovereignWorkbenchProcess -ProjectRoot $PSScriptRoot)
}

$existingWorkbench = Get-SovereignWorkbenchProcess -ProjectRoot $PSScriptRoot
if ($existingWorkbench -and $existingWorkbench.Legacy) {
    # A previous checkout environment can survive cleanup and serve stale code.
    Stop-SovereignWorkbenchProcess -Workbench $existingWorkbench
    Remove-Item -LiteralPath (Join-Path $PSScriptRoot 'benchmarks\workbench.pid') -ErrorAction SilentlyContinue
    $existingWorkbench = $null
}
if (-not (Get-NetTCPConnection -LocalPort 8088 -State Listen -ErrorAction SilentlyContinue)) {
    & (Join-Path $PSScriptRoot 'start-workbench.ps1')
} elseif (!$existingWorkbench) {
    throw 'Port 8088 is served by a workbench that this launcher does not own. Stop it in the application that started it before launching SovereignAI.'
} elseif (-not (Test-LocalHealth $app)) {
    throw 'Port 8088 is occupied, but the workbench is not healthy. Check the process before restarting it.'
}

if (-not (Get-NetTCPConnection -LocalPort 8087 -State Listen -ErrorAction SilentlyContinue)) {
    & (Join-Path $PSScriptRoot 'start-local-model.ps1') -IdleSeconds $IdleSeconds
} elseif (!(Test-OwnedModelListener)) {
    throw 'Port 8087 is serving a model that this SovereignAI launcher does not own. Stop it in the application that started it before launching SovereignAI.'
}

for ($attempt = 0; $attempt -lt 60; $attempt++) {
    if ((Test-LocalHealth $model) -and (Test-LocalHealth $app)) {
        if (!(Test-OwnedModelListener)) {
            throw 'Port 8087 is serving a model that this SovereignAI launcher does not own. Stop it in the application that started it before launching SovereignAI.'
        }
        $models = Invoke-RestMethod -Uri "$model/v1/models" -TimeoutSec 3
        if ($models.data.Count -eq 1 -and $models.data[0].id -eq 'sovereign-text') {
            Write-Output "SovereignAI is ready: $app"
            if (!$NoBrowser) {
                $chromeCandidates = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe")
                $chromePath = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
                if ($chromePath) { Start-Process -FilePath $chromePath -ArgumentList @("--app=$app",'--new-window') }
                else { Start-Process $app }
            }
            exit 0
        }
        throw 'A different model is active on port 8087. Finish the current task or switch back to sovereign-text before starting general chat.'
    }
    Start-Sleep -Seconds 1
}
throw 'The local model or workbench did not become ready within 60 seconds. Check benchmarks\server.stderr.log and benchmarks\workbench.stderr.log.'
