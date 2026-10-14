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
$dataRoot = Join-Path $taskRoot 'data'
New-Item -ItemType Directory -Path $dataRoot -Force | Out-Null
$configurationPath = Join-Path $dataRoot 'config.json'
$legacyConfiguration = Join-Path $taskRoot 'config.json'
if (-not (Test-Path -LiteralPath $configurationPath) -and (Test-Path -LiteralPath $legacyConfiguration)) {
    Move-Item -LiteralPath $legacyConfiguration -Destination $configurationPath
}
if (-not (Test-Path -LiteralPath $configurationPath)) {
    $cfg = Get-Content -LiteralPath (Join-Path $taskRoot 'config.example.json') -Raw | ConvertFrom-Json
    if (-not $cfg.speakers.PSObject.Properties.Count) { throw 'Configure at least one speaker in config.example.json.' }
    foreach ($entry in $cfg.speakers.PSObject.Properties) {
        $speakerName = $entry.Name
        $speaker = $entry.Value
        $info = [xml](Invoke-WebRequest ('http://' + $speaker.ip + ':8090/info') -UseBasicParsing -TimeoutSec 5).Content
        if ($info.info.name -ne $speakerName) { throw "A coluna em $($speaker.ip) chama-se $($info.info.name); atualize config.example.json." }
        $speaker.id = [string]$info.info.deviceID
        $speaker.model = [string]$info.info.type
    }
    if (-not $cfg.speakers.PSObject.Properties[$cfg.speaker_name]) {
        $cfg.speaker_name = ($cfg.speakers.PSObject.Properties | Select-Object -First 1).Name
    }
    $cfg.speaker_id = $cfg.speakers.($cfg.speaker_name).id
    $cfg.speaker_ip = $cfg.speakers.($cfg.speaker_name).ip
    $previousOutput = & $venvPython -c "from pycaw.pycaw import AudioUtilities; d=AudioUtilities.GetSpeakers(); print(d.id if 'VB-Audio Virtual Cable' not in d.FriendlyName else '')"
    if ($previousOutput) { $cfg | Add-Member -NotePropertyName previous_output -NotePropertyValue $previousOutput.Trim() }
    $jsonText = $cfg | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($configurationPath, $jsonText, (New-Object System.Text.UTF8Encoding($false)))
}
Write-Output 'Dependencies and configuration ready. See README.md to install VB-CABLE and configure the firewall.'
