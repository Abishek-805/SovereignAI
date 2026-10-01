param([Parameter(Mandatory=$true)][string]$Workspace,
      [Parameter(Mandatory=$true)][string]$Target)
$ErrorActionPreference = 'Stop'
$taskWorkspace = (Resolve-Path -LiteralPath $Workspace).Path
$taskProgram = (Resolve-Path -LiteralPath (Join-Path $taskWorkspace $Target)).Path
if (!$taskProgram.StartsWith($taskWorkspace.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase) -or
    [IO.Path]::GetExtension($taskProgram) -ne '.py') { throw 'Select a Python file inside the workspace.' }
$taskHasher = [Security.Cryptography.SHA256]::Create()
try {
    $taskEnvironmentId = [BitConverter]::ToString($taskHasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($taskWorkspace.ToLowerInvariant()))).Replace('-', '').ToLowerInvariant()
} finally { $taskHasher.Dispose() }
$taskEnvironment = Join-Path ([Environment]::GetFolderPath('MyDocuments')) "SovereignAI\Runtime\project-environments\$taskEnvironmentId"
$taskPython = Join-Path $taskEnvironment 'Scripts\python.exe'
if (!(Test-Path -LiteralPath $taskPython)) {
    $taskBundledPython = Join-Path (Split-Path $PSScriptRoot) '.app-venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $taskBundledPython) { & $taskBundledPython -m venv $taskEnvironment }
    else { py -3 -m venv $taskEnvironment }
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3 for Windows to run desktop programs.' }
}
Push-Location $taskWorkspace
try {
    $taskRequirements = Join-Path $taskWorkspace 'requirements.txt'
    if (Test-Path -LiteralPath $taskRequirements) {
        & $taskPython -m pip install -r $taskRequirements
        if ($LASTEXITCODE -ne 0) { throw 'Project dependency installation failed.' }
    }
    # Existing generated projects may predate dependency-file generation.
    $taskSource = Get-Content -LiteralPath $taskProgram -Raw
    if ($taskSource -match '(?m)^\s*(import\s+cv2\b|from\s+cv2\b)') {
        & $taskPython -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('cv2') else 1)"
        if ($LASTEXITCODE -ne 0) {
            & $taskPython -m pip install opencv-python==4.12.0.88
            if ($LASTEXITCODE -ne 0) { throw 'OpenCV installation failed.' }
        }
    }
    & $taskPython $taskProgram
    exit $LASTEXITCODE
} finally { Pop-Location }
