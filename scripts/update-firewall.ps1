$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Path (Join-Path $taskRoot 'data\reports') -Force | Out-Null
try {
    $ruleName = 'SoundTouch Quartos - audio local'
    $cfg = Get-Content -LiteralPath (Join-Path $taskRoot 'data\config.json') -Raw | ConvertFrom-Json
    $addresses = @($cfg.speakers.PSObject.Properties | ForEach-Object { $_.Value.ip } | Sort-Object -Unique)
    if ($addresses | Where-Object { [string]::IsNullOrWhiteSpace($_) }) { throw 'Configure os endereços das colunas primeiro.' }
    Get-NetFirewallRule -DisplayName $ruleName | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter -RemoteAddress $addresses | Out-Null
    @{ result = 'ok'; speakers = $addresses } | ConvertTo-Json | Set-Content (Join-Path $taskRoot 'data\reports\firewall.json') -Encoding UTF8
} catch {
    @{ error = $_.Exception.Message } | ConvertTo-Json | Set-Content (Join-Path $taskRoot 'data\reports\firewall.json') -Encoding UTF8
}
