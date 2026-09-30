<#
.SYNOPSIS
    Make Luna Tpx3 GUI (Qt 6) launchable with one double-click on Windows.

.DESCRIPTION
    Builds a private venv with everything in requirements.txt under
    %USERPROFILE%\venvs\<VenvName> (default: luna-tpx3-gui), then creates a
    Desktop (and optionally Start Menu) shortcut that runs the GUI through
    that venv's pythonw.exe -- no console window, no need to open PowerShell.
    Nothing outside the current user's profile is touched and no administrator
    rights are needed. Re-running is safe: an existing venv is reused and its
    packages brought up to date.

    This installs *this GUI only*. It never copies, moves or repackages the
    Luna binaries -- you point the GUI at your own Luna install at runtime.

.EXAMPLE
    .\install-windows.ps1
    .\install-windows.ps1 -StartMenu
    .\install-windows.ps1 -VenvName my-luna-env
    .\install-windows.ps1 -NoVenv
    .\install-windows.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [switch]$StartMenu,                  # also add it to the Start Menu
    [switch]$Uninstall,                  # remove the shortcuts this script created
    [switch]$NoVenv,                     # skip the venv; use a Python that already has PySide6
    [string]$VenvName = 'luna-tpx3-gui', # folder under %USERPROFILE%\venvs
    [string]$Python                      # explicit pythonw.exe to use (implies -NoVenv)
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
$reqs     = Join-Path $here 'requirements.txt'
$venvDir  = Join-Path $env:USERPROFILE ('venvs\' + $VenvName)
$venvPy   = Join-Path $venvDir 'Scripts\python.exe'
$venvPyw  = Join-Path $venvDir 'Scripts\pythonw.exe'
if ($Python) { $NoVenv = $true }

function Say($m) { Write-Host "  $m" }

# Run a native command with its stderr discarded. Windows PowerShell 5.1 turns
# redirected stderr lines into error records, which 'Stop' makes fatal -- a
# probe that is *expected* to fail would abort the whole script. So relax the
# preference for the call only. Returns stdout; $LASTEXITCODE is set as usual.
function Invoke-Quiet {
    param([string]$Exe, [string[]]$ArgList)
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Exe @ArgList 2>$null } finally { $ErrorActionPreference = $old }
}

# A real CPython 3.9+ to build the venv from. The py launcher goes first: it
# knows every installed CPython, and it is never the Microsoft Store stub that
# a bare "python.exe" on PATH can turn out to be.
function Find-BasePython {
    $probe = 'import sys, venv; assert sys.version_info >= (3, 9); print(sys.executable)'
    $tries = @()
    if (Get-Command py.exe -ErrorAction SilentlyContinue)     { $tries += ,@('py.exe', '-3') }
    if (Get-Command python.exe -ErrorAction SilentlyContinue) { $tries += ,@('python.exe') }
    foreach ($t in $tries) {
        $out = Invoke-Quiet $t[0] (@($t | Select-Object -Skip 1) + @('-c', $probe))
        if ($LASTEXITCODE -eq 0 -and $out) { return (@($out)[-1]).Trim() }
    }
    return $null
}

# ------------------------------------------------------------------ uninstall
if ($Uninstall) {
    $n = 0
    foreach ($t in $targets) {
        if (Test-Path $t) { Remove-Item $t -Force; Say "removed    : $t"; $n++ }
    }
    if ($n -eq 0) { Say 'nothing to remove' }
    if (Test-Path $venvDir) {
        Say "the private venv is still at $venvDir"
        Say "delete it yourself if you want the space back:  Remove-Item -Recurse '$venvDir'"
    }
    Say "The GUI's own files in $here were left alone."
    exit 0
}

if (-not (Test-Path $script)) { Write-Error "Not found: $script"; exit 1 }

# ------------------------------------------------------------------ venv (default)
if (-not $NoVenv) {
    Write-Host 'Building a private venv (PySide6 + the Inspect tab stack)...'
    Say "location   : $venvDir"
    Say '(skip with -NoVenv if a Python with PySide6 is already installed)'
    if (Test-Path $venvPy) {
        Say 'venv exists; bringing its packages up to date'
    } else {
        $base = Find-BasePython
        if (-not $base) {
            Write-Error @"
No Python 3.9+ was found to build the venv from.

Install Python from https://www.python.org/downloads/ (keep the "py launcher"
option ticked), then re-run this script.
"@
            exit 1
        }
        Say "base Python: $base"
        New-Item -ItemType Directory -Force -Path (Split-Path $venvDir) | Out-Null
        & $base -m venv $venvDir
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPy)) {
            Write-Error "Could not create the venv at $venvDir"
            exit 1
        }
    }
    # A failed pip self-upgrade is harmless; a failed requirements install is not.
    Invoke-Quiet $venvPy @('-m', 'pip', 'install', '--quiet', '--upgrade', 'pip') | Out-Null
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & $venvPy -m pip install --quiet -r $reqs    # stderr stays visible: it explains a failure
    $ErrorActionPreference = $old
    if ($LASTEXITCODE -ne 0) {
        Write-Error @"
pip could not install requirements.txt into $venvDir.

Check the network connection (and any proxy), then re-run this script. To use
a Python you have already set up instead:
    .\install-windows.ps1 -NoVenv
"@
        exit 1
    }
    Say 'venv ready (~450 MB); run_gui.bat picks it up too'
}

# ------------------------------------------------------------------ interpreter
# With the venv: its pythonw, nothing else. With -NoVenv: -Python, an existing
# venv from an earlier run, the tpx4cam venv, any pythonw on PATH. Either way
# the interpreter must actually import PySide6, otherwise the shortcut would
# fail silently -- with pythonw there is no console for the traceback to land in.
$cands = @()
if (-not $NoVenv) {
    $cands += $venvPyw
} else {
    if ($Python)  { $cands += $Python }
    $cands += $venvPyw
    $cands += Join-Path $env:USERPROFILE 'venvs\tpx4cam\Scripts\pythonw.exe'
    $cands += (Get-Command pythonw.exe -ErrorAction SilentlyContinue | ForEach-Object Source)
}

$pythonw = $null
foreach ($c in $cands) {
    if (-not $c -or -not (Test-Path $c)) { continue }
    $exe = $c -replace 'pythonw\.exe$', 'python.exe'      # test with the console build
    if (-not (Test-Path $exe)) { $exe = $c }
    Invoke-Quiet $exe @('-c', 'import PySide6') | Out-Null
    if ($LASTEXITCODE -eq 0) { $pythonw = $c; break }
    Say "skipped    : $c (no PySide6)"
}
if (-not $pythonw) {
    Write-Error @"
No Python with PySide6 was found.

Re-run without -NoVenv to build a private venv with everything, or install
the dependencies into the interpreter you want to use:
    py -3 -m pip install -r requirements.txt

and point this script at it explicitly:
    .\install-windows.ps1 -Python C:\path\to\pythonw.exe
"@
    exit 1
}

# ------------------------------------------------------------------ icon
# .lnk wants a real .ico; derive one from the 1024x1024 png once.
if (-not (Test-Path $icoIcon) -and (Test-Path $pngIcon)) {
    $py = $pythonw -replace 'pythonw\.exe$', 'python.exe'
    Invoke-Quiet $py @('-c', @"
from PIL import Image
im = Image.open(r'$pngIcon').convert('RGBA')
im.save(r'$icoIcon', format='ICO',
        sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
"@) | Out-Null
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
