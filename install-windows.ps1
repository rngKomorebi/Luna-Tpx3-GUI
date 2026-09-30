<#
.SYNOPSIS
    Make Luna Tpx3 GUI (Qt 6) launchable with one double-click on Windows.

.DESCRIPTION
    Creates a Desktop (and optionally Start Menu) shortcut that runs the GUI
    through pythonw.exe, so there is no console window and no need to open
    PowerShell. Nothing outside the current user's profile is touched and no
    administrator rights are needed.

    This installs *this GUI only*. It never copies, moves or repackages the
    Luna binaries -- you point the GUI at your own Luna install at runtime.

.EXAMPLE
    .\install-windows.ps1
    .\install-windows.ps1 -StartMenu
    .\install-windows.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [switch]$StartMenu,     # also add it to the Start Menu
    [switch]$Uninstall,     # remove the shortcuts this script created
    [string]$Python         # explicit pythonw.exe to use
)

$ErrorActionPreference = 'Stop'
$here     = Split-Path -Parent $MyInvocation.MyCommand.Path
$script   = Join-Path $here 'src\main.py'
$pngIcon  = Join-Path $here 'src\luna_tpx3_gui\icon\screen.png'
$icoIcon  = Join-Path $here 'src\luna_tpx3_gui\icon\luna-tpx3-gui.ico'
$lnkName  = 'Luna Tpx3 GUI.lnk'
$desktop  = [Environment]::GetFolderPath('Desktop')
$startDir = Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs'
$targets  = @((Join-Path $desktop $lnkName), (Join-Path $startDir $lnkName))

function Say($m) { Write-Host "  $m" }

# ------------------------------------------------------------------ uninstall
if ($Uninstall) {
    $n = 0
    foreach ($t in $targets) {
        if (Test-Path $t) { Remove-Item $t -Force; Say "removed    : $t"; $n++ }
    }
    if ($n -eq 0) { Say 'nothing to remove' }
    Say "The GUI's own files in $here were left alone."
    exit 0
}

# ------------------------------------------------------------------ interpreter
# Order: -Python, the tpx4cam venv, any pythonw on PATH. The interpreter must
# actually import PySide6, otherwise the shortcut would fail silently -- with
# pythonw there is no console for the traceback to land in.
$cands = @()
if ($Python)  { $cands += $Python }
$cands += Join-Path $env:USERPROFILE 'venvs\tpx4cam\Scripts\pythonw.exe'
$cands += (Get-Command pythonw.exe -ErrorAction SilentlyContinue | ForEach-Object Source)

$pythonw = $null
foreach ($c in $cands) {
    if (-not $c -or -not (Test-Path $c)) { continue }
    $exe = $c -replace 'pythonw\.exe$', 'python.exe'      # test with the console build
    if (-not (Test-Path $exe)) { $exe = $c }
    & $exe -c 'import PySide6' 2>$null
    if ($LASTEXITCODE -eq 0) { $pythonw = $c; break }
    Say "skipped    : $c (no PySide6)"
}
if (-not $pythonw) {
    Write-Error @"
No Python with PySide6 was found.

Install it into the interpreter you want to use:
    py -3 -m pip install PySide6 h5py numpy pandas matplotlib

then re-run this script, or point it at one explicitly:
    .\install-windows.ps1 -Python C:\path\to\pythonw.exe
"@
    exit 1
}
if (-not (Test-Path $script)) { Write-Error "Not found: $script"; exit 1 }

# ------------------------------------------------------------------ icon
# .lnk wants a real .ico; derive one from the 1024x1024 png once.
if (-not (Test-Path $icoIcon) -and (Test-Path $pngIcon)) {
    $py = $pythonw -replace 'pythonw\.exe$', 'python.exe'
    & $py -c @"
from PIL import Image
im = Image.open(r'$pngIcon').convert('RGBA')
im.save(r'$icoIcon', format='ICO',
        sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
"@ 2>$null
    if ($LASTEXITCODE -eq 0) { Say "icon       : generated $icoIcon" }
    else { Say 'icon       : Pillow not available, using the default icon' }
}

# ------------------------------------------------------------------ shortcuts
$wanted = @(Join-Path $desktop $lnkName)
if ($StartMenu) { $wanted += Join-Path $startDir $lnkName }

$shell = New-Object -ComObject WScript.Shell
foreach ($t in $wanted) {
    New-Item -ItemType Directory -Force -Path (Split-Path $t) | Out-Null
    $s = $shell.CreateShortcut($t)
    $s.TargetPath       = $pythonw
    $s.Arguments        = '"' + $script + '"'
    $s.WorkingDirectory = $here
    $s.Description      = 'Luna Tpx3 GUI - batch tpx3dump front end'
    if (Test-Path $icoIcon) { $s.IconLocation = "$icoIcon,0" }
    $s.Save()
    Say "shortcut   : $t"
}
Say "interpreter: $pythonw"
Say ''
Say 'Done. Double-click the Desktop shortcut to start the GUI.'
Say 'Undo with:  .\install-windows.ps1 -Uninstall'
