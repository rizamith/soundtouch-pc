param([string]$PythonCommand = 'python')
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$venvPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $PythonCommand -m venv (Join-Path $taskRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível criar o ambiente Python.' }
}
& $venvPython -m pip install -r (Join-Path $taskRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Falha na instalação das dependências.' }
$configurationPath = Join-Path $taskRoot 'config.json'
if (-not (Test-Path -LiteralPath $configurationPath)) {
    $cfg = Get-Content -LiteralPath (Join-Path $taskRoot 'config.example.json') -Raw | ConvertFrom-Json
    foreach ($speakerName in @('Quartos', 'Sala')) {
        $speaker = $cfg.speakers.$speakerName
        $info = [xml](Invoke-WebRequest ('http://' + $speaker.ip + ':8090/info') -UseBasicParsing -TimeoutSec 5).Content
        if ($info.info.name -ne $speakerName) { throw "A coluna em $($speaker.ip) chama-se $($info.info.name); atualize config.example.json." }
        $speaker.id = [string]$info.info.deviceID
        $speaker.model = [string]$info.info.type
    }
    $cfg.speaker_id = $cfg.speakers.Quartos.id
    $cfg.speaker_ip = $cfg.speakers.Quartos.ip
    $previousOutput = & $venvPython -c "from pycaw.pycaw import AudioUtilities; d=AudioUtilities.GetSpeakers(); print(d.id if 'VB-Audio Virtual Cable' not in d.FriendlyName else '')"
    if ($previousOutput) { $cfg | Add-Member -NotePropertyName previous_output -NotePropertyValue $previousOutput.Trim() }
    $jsonText = $cfg | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($configurationPath, $jsonText, (New-Object System.Text.UTF8Encoding($false)))
}
Write-Output 'Dependências e configuração prontas. Consulte README.md para instalar o VB-CABLE e configurar a firewall.'
