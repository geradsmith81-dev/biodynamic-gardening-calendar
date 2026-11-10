# Creates the app icon: a shortcut "Biodynamic Gardening Calendar" on the Desktop and in the Start menu.
# Run it by double-clicking "Create desktop icon.bat" in the app folder. Run it again after moving the folder.
param([string[]]$Destinations)
$ErrorActionPreference = 'Stop'
$app  = Split-Path -Parent $PSScriptRoot                     # the folder that holds app.py
$bat  = Join-Path $app 'Start app.bat'
$ico  = Join-Path $app 'assets\houseplant_icon.ico'
foreach ($f in @($bat, $ico)) { if (-not (Test-Path $f)) { throw "Missing file: $f" } }
if (-not $Destinations) {
    $Destinations = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))
}
$name  = "Biodynamic Gardening Calendar.lnk"
$old   = @("Biodynamic Houseplant Calendar.lnk")   # the icon's earlier name: removed so there are not two icons
$shell = New-Object -ComObject WScript.Shell
foreach ($dir in $Destinations) {
    foreach ($o in $old) {
        $oldPath = Join-Path $dir $o
        if (Test-Path -LiteralPath $oldPath) { Remove-Item -LiteralPath $oldPath; Write-Host "  Removed the old icon: $oldPath" }
    }
    $path = Join-Path $dir $name
    $lnk = $shell.CreateShortcut($path)
    # cmd.exe as the target (not the .bat itself) so that Windows allows "Pin to taskbar"
    $lnk.TargetPath       = Join-Path $env:SystemRoot 'System32\cmd.exe'
    $lnk.Arguments        = '/c ""' + $bat + '""'
    $lnk.WorkingDirectory = $app
    $lnk.IconLocation     = "$ico,0"
    $lnk.WindowStyle      = 7                                   # start the black window minimised
    $lnk.Description      = "Biodynamic Gardening Calendar: best times to sow, repot and harvest by the Moon in the IAU constellations"
    $lnk.Save()
    Write-Host "  Created: $path"
}
