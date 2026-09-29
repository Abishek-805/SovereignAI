param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot
$python = Join-Path $taskRoot '.app-venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Install requirements.txt in .app-venv first; see README.' }
$dockerCommand = Get-Command docker -ErrorAction Stop
$engine = 'npipe:////./pipe/dockerDesktopLinuxEngine'
Push-Location $taskRoot
try {
    & $dockerCommand.Source --host $engine info --format '{{.OSType}}'
    if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop with the Linux engine first.' }
    if (!$SkipBuild) {
        & $dockerCommand.Source --host $engine build -f offline/Dockerfile.workbench -t sovereign-workbench .
        if ($LASTEXITCODE -ne 0) { throw 'Sandbox build failed; the previous verified image remains active.' }
    }
    $candidateImage = & $dockerCommand.Source --host $engine image inspect sovereign-workbench --format '{{.Id}}'
    if ($LASTEXITCODE -ne 0 -or $candidateImage -notmatch '^sha256:[a-f0-9]{64}$') { throw 'No pinned candidate image is available.' }
    & $python -m scripts.verify_workbench_languages --image $candidateImage
    if ($LASTEXITCODE -ne 0) { throw 'A language check failed; the previous verified image remains active.' }
    & $python -m scripts.verify_docker_sandbox $candidateImage
    if ($LASTEXITCODE -ne 0) { throw 'Sandbox isolation checks failed; the previous verified image remains active.' }
    Write-Output "Verified and activated sandbox $candidateImage"
} finally { Pop-Location }
