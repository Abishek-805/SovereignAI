function Get-SovereignWorkbenchProcess {
    param([string]$ProjectRoot)

    $listener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8088 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (!$listener) { return $null }

    $child = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
    if (!$child) { return $null }
    $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($child.ParentProcessId)" -ErrorAction SilentlyContinue
    if (!$parent) { return $null }

    # A Windows venv python.exe starts the base interpreter as a child. The
    # parent executable identifies this checkout even if its PID file was lost.
    $knownInterpreters = @('.app-venv', '.venv', '.venv314') | ForEach-Object {
        [IO.Path]::GetFullPath((Join-Path $ProjectRoot "$_\Scripts\python.exe"))
    }
    $sameProject = $knownInterpreters | Where-Object { $_ -ieq $parent.ExecutablePath }
    $launch = '-m uvicorn backend.app:create_app --factory --host 127.0.0.1 --port 8088'
    if (!$sameProject -or !$parent.CommandLine.Contains($launch) -or !$child.CommandLine.Contains($launch)) { return $null }

    return [pscustomobject]@{
        ParentId = [int]$parent.ProcessId
        ListenerId = [int]$child.ProcessId
        Legacy = $parent.ExecutablePath -ine (Join-Path $ProjectRoot '.app-venv\Scripts\python.exe')
    }
}

function Stop-SovereignWorkbenchProcess {
    param($Workbench)
    if (!$Workbench) { return }
    Stop-Process -Id $Workbench.ListenerId -ErrorAction SilentlyContinue
    Stop-Process -Id $Workbench.ParentId -ErrorAction SilentlyContinue
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        if (!(Get-NetTCPConnection -LocalPort 8088 -State Listen -ErrorAction SilentlyContinue)) { return }
        Start-Sleep -Milliseconds 250
    }
    throw 'The SovereignAI workbench did not release port 8088.'
}
