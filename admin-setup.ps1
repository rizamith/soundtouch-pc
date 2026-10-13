$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$result = Join-Path $taskRoot 'admin-result.json'
try {
    $ruleName = 'SoundTouch Quartos - audio local'
    $cfg = Get-Content -LiteralPath (Join-Path $taskRoot 'config.json') -Raw | ConvertFrom-Json
    $addresses = @($cfg.speakers.Quartos.ip, $cfg.speakers.Sala.ip)
    if ($addresses | Where-Object { [string]::IsNullOrWhiteSpace($_) }) { throw 'Configure os endereços das colunas primeiro.' }
    if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $cfg.port -RemoteAddress $addresses -Profile Any | Out-Null
    } else {
        Get-NetFirewallRule -DisplayName $ruleName | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter -RemoteAddress $addresses | Out-Null
    }
    @{ firewall = 'ok'; driver = 'pending'; message = 'Abra o instalador VB-CABLE, clique Install Driver e feche quando concluir.' } | ConvertTo-Json | Set-Content -LiteralPath $result -Encoding UTF8
    $cablePresent = Get-PnpDevice -Class MEDIA -ErrorAction SilentlyContinue | Where-Object FriendlyName -Like '*VB-Audio Virtual Cable*'
    if (-not $cablePresent) {
        $installer = Join-Path $taskRoot 'vendor\vbcable\VBCABLE_Setup_x64.exe'
        if (-not (Test-Path -LiteralPath $installer)) { throw 'Descarregue VB-CABLE do site oficial e extraia para vendor\vbcable, conforme README.md.' }
        if ((Get-AuthenticodeSignature -LiteralPath $installer).Status -ne 'Valid') { throw 'Assinatura do instalador inválida.' }
        # This is an interactive driver installer; its window must be visible.
        Start-Process -FilePath $installer -Wait
    }
    & (Join-Path $taskRoot '.venv\Scripts\python.exe') (Join-Path $taskRoot 'name-output.py')
    $renamed = $LASTEXITCODE -eq 0
    @{ firewall = 'ok'; driver = $(if ($renamed) {'installed'} else {'reboot-or-install-required'}); renamed = $renamed } | ConvertTo-Json | Set-Content -LiteralPath $result -Encoding UTF8
} catch {
    @{ error = $_.Exception.Message } | ConvertTo-Json | Set-Content -LiteralPath $result -Encoding UTF8
}
