$ErrorActionPreference = 'Stop'
try {
    $ruleName = 'SoundTouch Quartos - audio local'
    $cfg = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'config.json') -Raw | ConvertFrom-Json
    $addresses = @($cfg.speakers.Quartos.ip, $cfg.speakers.Sala.ip)
    if ($addresses | Where-Object { [string]::IsNullOrWhiteSpace($_) }) { throw 'Configure os endereços das colunas primeiro.' }
    Get-NetFirewallRule -DisplayName $ruleName | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter -RemoteAddress $addresses | Out-Null
    @{ result = 'ok'; speakers = $addresses } | ConvertTo-Json | Set-Content (Join-Path $PSScriptRoot 'sala-firewall.json') -Encoding UTF8
} catch {
    @{ error = $_.Exception.Message } | ConvertTo-Json | Set-Content (Join-Path $PSScriptRoot 'sala-firewall.json') -Encoding UTF8
}
