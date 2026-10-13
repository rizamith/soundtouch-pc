param([switch]$Panel)
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$python = Join-Path $taskRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run setup.ps1 first to create the Python environment.' }
$appArguments = @('"' + (Join-Path $taskRoot 'app\bridge.py') + '"')
if ($Panel) { $appArguments += '--panel' }
Start-Process -FilePath $python -ArgumentList $appArguments -WorkingDirectory $taskRoot -WindowStyle Hidden
