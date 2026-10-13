$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$diagnosticsRoot = Join-Path $taskRoot 'data\reports'
New-Item -ItemType Directory -Path $diagnosticsRoot -Force | Out-Null
$reportPath = Join-Path $diagnosticsRoot 'realtek-restart.json'
try {
    $device = Get-PnpDevice -Class MEDIA | Where-Object { $_.FriendlyName -like '*Realtek*' -and $_.InstanceId -like 'HDAUDIO\FUNC_01&VEN_10EC&DEV_0255&SUBSYS_10438768*' } | Select-Object -First 1
    if (-not $device) { throw 'Realtek do ASUS PB60 não encontrado.' }
    $driver = Get-PnpDeviceProperty -InstanceId $device.InstanceId -KeyName DEVPKEY_Device_DriverInfPath
    $backupDir = Join-Path $taskRoot 'data\backups\realtek-driver'
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    $exportOutput = & pnputil.exe /export-driver $driver.Data $backupDir 2>&1
    if ($LASTEXITCODE -ne 0) { throw ('Falha ao guardar driver: ' + ($exportOutput -join ' ')) }
    $restartOutput = & pnputil.exe /restart-device $device.InstanceId 2>&1
    $restartCode = $LASTEXITCODE
    @{ device = $device.InstanceId; driver = $driver.Data; backup = $backupDir; exitCode = $restartCode; output = ($restartOutput -join "`n") } | ConvertTo-Json | Set-Content -LiteralPath $reportPath -Encoding UTF8
} catch {
    @{ error = $_.Exception.Message } | ConvertTo-Json | Set-Content -LiteralPath $reportPath -Encoding UTF8
}
