$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$shortcutShell = New-Object -ComObject WScript.Shell
$places = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Startup'))
foreach ($place in $places) {
    $shortcut = $shortcutShell.CreateShortcut((Join-Path $place 'SoundTouch.lnk'))
    $shortcut.TargetPath = Join-Path $taskRoot '.venv\Scripts\pythonw.exe'
    $shortcut.Arguments = '"' + (Join-Path $taskRoot 'app\bridge.py') + '"'
    $shortcut.WorkingDirectory = $taskRoot
    if (Test-Path (Join-Path $taskRoot 'data\assets\soundtouch.ico')) {
        $shortcut.IconLocation = (Join-Path $taskRoot 'data\assets\soundtouch.ico') + ',0'
    }
    $shortcut.Description = 'Ouvir o PC nas colunas Bose Quartos ou Sala por Wi-Fi'
    $shortcut.Save()
    $previousShortcut = Join-Path $place 'SoundTouch Quartos.lnk'
    if (Test-Path -LiteralPath $previousShortcut) {
        Remove-Item -LiteralPath $previousShortcut
    }
}
Write-Output 'Atalhos criados no Ambiente de Trabalho e no arranque do Windows.'
