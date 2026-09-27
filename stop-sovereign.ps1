$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'stop-workbench.ps1')
& (Join-Path $PSScriptRoot 'stop-local-model.ps1')
