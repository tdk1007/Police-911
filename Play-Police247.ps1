<#
.SYNOPSIS
  One-shot launcher for Police 24/7 (PAL) with body-motion + OpenFIRE lightgun.

.DESCRIPTION
  Brings the whole stack up in the right order:
    1. Verifies a PS2 BIOS is present (auto-fills PCSX2.ini the first time).
    2. Patches PCSX2's USB Port 1 for the chosen motion mode:
         camera  -> emulated Konami Capture Eye fed by a real capture device
                    (the authentic in-game motion sensing, incl. graduated lean)
         bridge  -> no emulated camera; starts the Python head-tracking bridge,
                    which holds K (= pad Square = cover) while you duck
         none    -> gun only; duck manually with K
    3. Optionally starts OBS with its Virtual Camera (-Obs) as the normalized
       4:3 feed for the emulated Capture Eye.
    4. Boots PCSX2 fullscreen straight into the game.

.EXAMPLES
  .\Play-Police247.ps1                          # authentic camera path, direct
  .\Play-Police247.ps1 -Obs                     # camera path via OBS VirtualCam
  .\Play-Police247.ps1 -Motion bridge           # CV-bridge fallback path
  .\Play-Police247.ps1 -Motion bridge -BridgeSource udp   # iPhone ARKit path
  .\Play-Police247.ps1 -Motion none             # gun only
  .\Play-Police247.ps1 -Phone                   # use the iPhone as the light gun
  .\Play-Police247.ps1 -Gui                     # show the launch checkbox dialog
  .\Play-Police247.ps1 -DryRun                  # show what would happen
#>
param(
    [ValidateSet('camera', 'bridge', 'none')]
    [string]$Motion = 'camera',
    [string]$CameraName = '',           # DirectShow friendly name override
    [switch]$Obs,                       # use OBS Virtual Camera as the feed
    [ValidateSet('webcam', 'udp')]
    [string]$BridgeSource = 'webcam',
    [switch]$Phone,                     # iPhone-as-lightgun: start the UDP->mouse helper
    [switch]$Gui,                       # show a checkbox dialog before launching
    [switch]$NoFullscreen,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$Root   = Split-Path -Parent $MyInvocation.MyCommand.Path
$Pcsx2  = Join-Path $Root 'PCSX2\pcsx2-qt.exe'
$Ini    = Join-Path $Root 'PCSX2\inis\PCSX2.ini'
$BiosDir = Join-Path $Root 'PCSX2\bios'
# PCSX2 cannot parse .cue files — boot the raw MODE2/2352 .bin directly
# (single data track; the XA audio is interleaved in it, nothing is lost)
$Game   = Join-Path $Root 'Police 24-7 (Europe) (En,Fr,De,Es,It)\Police 24-7 (Europe) (En,Fr,De,Es,It).bin'
$Bridge = Join-Path $Root 'bridge\police247_bridge.py'
$GunHelper = Join-Path $Root 'iPhone Gun\windows\gun_helper.py'
$PhonePref = Join-Path $Root '.launcher-phone.pref'   # remembers the checkbox state

# Track what WE launch so we can shut it down when the game quits
$script:StartedObs = $false
$script:ObsProc    = $null
$script:GunProc    = $null

# ---------------------------------------------------------------- ini helpers
function Set-IniValue([string]$Path, [string]$Section, [string]$Key, [string]$Value) {
    $lines = @(Get-Content -LiteralPath $Path)
    $out = New-Object System.Collections.Generic.List[string]
    $inSection = $false; $done = $false; $sectionSeen = $false
    foreach ($line in $lines) {
        if ($line -match '^\s*\[(.+)\]\s*$') {
            if ($inSection -and -not $done) { $out.Add("$Key = $Value"); $done = $true }
            $inSection = ($Matches[1] -eq $Section)
            if ($inSection) { $sectionSeen = $true }
            $out.Add($line); continue
        }
        if ($inSection -and -not $done -and $line -match "^\s*$([regex]::Escape($Key))\s*=") {
            $out.Add("$Key = $Value"); $done = $true; continue
        }
        $out.Add($line)
    }
    if (-not $done) {
        if (-not $sectionSeen) { $out.Add(''); $out.Add("[$Section]") }
        elseif ($inSection) { }  # section was last; just append
        $out.Add("$Key = $Value")
    }
    Set-Content -LiteralPath $Path -Value $out -Encoding ascii
}

function Get-IniValue([string]$Path, [string]$Section, [string]$Key) {
    $inSection = $false
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^\s*\[(.+)\]\s*$') { $inSection = ($Matches[1] -eq $Section); continue }
        if ($inSection -and $line -match "^\s*$([regex]::Escape($Key))\s*=\s*(.*)$") { return $Matches[1].Trim() }
    }
    return $null
}

# ------------------------------------------------------------- phone (gun) path
# Best-effort LAN IPv4 so the dialog can tell the user what to type in the app.
function Get-LanIPv4 {
    try {
        $ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' -and $_.PrefixOrigin -ne 'WellKnown' } |
            Sort-Object InterfaceMetric | Select-Object -First 1 -ExpandProperty IPAddress
        if ($ip) { return $ip }
    } catch {}
    return '<this PC''s IP>'
}

# Find a Python launcher (prefer the py launcher, fall back to python on PATH).
function Get-PythonCmd {
    foreach ($c in @(
        @{ Exe = 'py';     Args = @('-3') },
        @{ Exe = 'python'; Args = @() }
    )) {
        if (Get-Command $c.Exe -ErrorAction SilentlyContinue) { return $c }
    }
    return $null
}

# Start the iPhone->mouse helper in its own window (it prints connection stats).
function Start-GunHelper {
    if (-not (Test-Path -LiteralPath $GunHelper)) {
        Write-Host "Phone gun requested but helper not found: $GunHelper" -ForegroundColor Red
        return
    }
    $py = Get-PythonCmd
    if (-not $py) {
        Write-Host 'Phone gun requested but Python was not found on PATH.' -ForegroundColor Red
        Write-Host '  Install it: winget install Python.Python.3.12' -ForegroundColor Yellow
        return
    }
    Write-Host "Phone gun: starting helper ($($py.Exe)) <- listens UDP :52777"
    Write-Host "  In the iPhone app, set PC IP = $(Get-LanIPv4), port 52777, tap Start."
    if (-not $DryRun) {
        $argList = @($py.Args + @('"' + $GunHelper + '"'))
        $script:GunProc = Start-Process -FilePath $py.Exe -ArgumentList $argList `
            -WorkingDirectory (Split-Path $GunHelper) -PassThru
        Start-Sleep -Milliseconds 400
    }
}

# OBS marks a crash if it finds a leftover run_* file in .sentinel (which a
# force-kill orphans) -> next launch shows the "Safe Mode" dialog and, worse,
# a hard-kill while the vcam runs sticks the virtual camera until reboot. These
# helpers keep OBS shutting down cleanly so that never happens.
function Clear-ObsCrashSentinels {
    if (Get-Process obs64 -ErrorAction SilentlyContinue) { return }  # don't touch a live run
    $sdir = Join-Path $env:APPDATA 'obs-studio\.sentinel'
    Get-ChildItem $sdir -Filter 'run_*' -Force -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

# Force ConfirmOnExit=false so we can close OBS with WM_CLOSE without a modal
# blocking the graceful shutdown. Preserves the file's UTF-8 BOM.
function Set-ObsCleanExit {
    $ini = Join-Path $env:APPDATA 'obs-studio\user.ini'
    if (-not (Test-Path -LiteralPath $ini)) { return }
    $txt = [System.IO.File]::ReadAllText($ini)
    if ($txt -match '(?im)^\s*ConfirmOnExit\s*=') {
        $txt = [regex]::Replace($txt, '(?im)^\s*ConfirmOnExit\s*=.*$', 'ConfirmOnExit=false')
    } elseif ($txt -match '(?im)^\[General\]') {
        $txt = [regex]::Replace($txt, '(?im)^\[General\][^\r\n]*', "`$0`r`nConfirmOnExit=false", 1)
    } else {
        $txt = "[General]`r`nConfirmOnExit=false`r`n" + $txt
    }
    [System.IO.File]::WriteAllText($ini, $txt, (New-Object System.Text.UTF8Encoding($true)))
}

# Close OBS the clean way (WM_CLOSE) so it deletes its own sentinel and releases
# the virtual camera; force-kill only as a last resort, then scrub the sentinel.
function Stop-ObsGracefully([System.Diagnostics.Process]$proc, [int]$TimeoutSec = 10) {
    if (-not $proc) { $proc = Get-Process obs64 -ErrorAction SilentlyContinue | Select-Object -First 1 }
    if (-not $proc) { return }
    try { $proc.Refresh(); [void]$proc.CloseMainWindow() } catch {}
    if (-not $proc.WaitForExit($TimeoutSec * 1000)) {
        Write-Host 'OBS did not close in time; forcing (will scrub the crash sentinel).' -ForegroundColor Yellow
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 400
    Clear-ObsCrashSentinels
}

# Wait until OBS's Virtual Camera is actually live before PCSX2 enumerates
# devices. Gates on the OBS log ("Virtual Camera Start") instead of a blind
# sleep — otherwise PCSX2 can race OBS and fall back to the "Insta360 Virtual
# Camera" filter, which letterboxes 16:9 into 4:3 (black bars top/bottom).
function Wait-ObsVirtualCam([int]$TimeoutSec = 20) {
    $logDir = Join-Path $env:APPDATA 'obs-studio\logs'
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        $log = Get-ChildItem -LiteralPath $logDir -Filter '*.txt' -ErrorAction SilentlyContinue |
               Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($log -and (Select-String -LiteralPath $log.FullName `
                -Pattern 'Virtual Camera Start|Virtual output started' -Quiet)) {
            Write-Host "OBS Virtual Camera confirmed live ($($log.Name))."
            Start-Sleep -Milliseconds 800   # small settle before PCSX2 opens it
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    Write-Host 'WARNING: could not confirm OBS Virtual Camera started in time;' -ForegroundColor Yellow
    Write-Host '         the game may fall back to a letterboxed feed. Check OBS.' -ForegroundColor Yellow
    return $false
}

# WinForms checkbox dialog. Returns $true = play, $false = cancel; sets the
# script-scoped $Phone as a side effect. Remembers the last checkbox state.
function Show-LauncherDialog {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $lastPhone = $false
    if (Test-Path -LiteralPath $PhonePref) {
        $lastPhone = ((Get-Content -LiteralPath $PhonePref -Raw).Trim() -eq '1')
    }

    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'Police 24/7 Launcher'
    $form.FormBorderStyle = 'FixedDialog'
    $form.StartPosition = 'CenterScreen'
    $form.MaximizeBox = $false; $form.MinimizeBox = $false
    $form.ClientSize = New-Object System.Drawing.Size(380, 150)

    $chk = New-Object System.Windows.Forms.CheckBox
    $chk.Text = 'Use iPhone as the light gun (aim + trigger over WiFi)'
    $chk.AutoSize = $true
    $chk.Checked = ($lastPhone -or $Phone)
    $chk.Location = New-Object System.Drawing.Point(20, 25)

    $hint = New-Object System.Windows.Forms.Label
    $hint.AutoSize = $false
    $hint.Location = New-Object System.Drawing.Point(40, 50)
    $hint.Size = New-Object System.Drawing.Size(320, 34)
    $hint.ForeColor = [System.Drawing.Color]::DimGray
    $hint.Text = "In the PoliceGun app, set PC IP = $(Get-LanIPv4), port 52777.`nUnchecked = play with the desk mouse / OpenFIRE gun."

    $play = New-Object System.Windows.Forms.Button
    $play.Text = 'Play'; $play.Location = New-Object System.Drawing.Point(200, 105)
    $play.Size = New-Object System.Drawing.Size(75, 28)
    $play.DialogResult = [System.Windows.Forms.DialogResult]::OK

    $cancel = New-Object System.Windows.Forms.Button
    $cancel.Text = 'Cancel'; $cancel.Location = New-Object System.Drawing.Point(285, 105)
    $cancel.Size = New-Object System.Drawing.Size(75, 28)
    $cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel

    $form.Controls.AddRange(@($chk, $hint, $play, $cancel))
    $form.AcceptButton = $play; $form.CancelButton = $cancel

    $result = $form.ShowDialog()
    if ($result -ne [System.Windows.Forms.DialogResult]::OK) { return $false }

    $script:Phone = $chk.Checked
    Set-Content -LiteralPath $PhonePref -Value $(if ($chk.Checked) { '1' } else { '0' }) -Encoding ascii
    return $true
}

# ------------------------------------------------------------------ preflight
foreach ($p in @($Pcsx2, $Ini, $Game)) {
    if (-not (Test-Path -LiteralPath $p)) { throw "Missing required file: $p" }
}

# BIOS: auto-fill [Filenames] BIOS with the first plausible dump in PCSX2\bios
$bios = Get-IniValue $Ini 'Filenames' 'BIOS'
if (-not $bios -or -not (Test-Path -LiteralPath (Join-Path $BiosDir $bios))) {
    $cand = Get-ChildItem -LiteralPath $BiosDir -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in '.bin', '.BIN', '.rom0' -or $_.Name -match '^scph|^SCPH|^ps2' } |
        Where-Object { $_.Length -ge 512KB } | Select-Object -First 1
    if (-not $cand) {
        Write-Host ''
        Write-Host 'NO PS2 BIOS FOUND.' -ForegroundColor Red
        Write-Host "Copy your PS2 BIOS dump (e.g. SCPH-70004 EU, a ~4 MB .bin) into:"
        Write-Host "  $BiosDir" -ForegroundColor Yellow
        Write-Host 'then run this script again. (Dump it from your own console — see README.)'
        exit 1
    }
    Write-Host "BIOS: using $($cand.Name)"
    if (-not $DryRun) { Set-IniValue $Ini 'Filenames' 'BIOS' $cand.Name }
}

# ------------------------------------------------------ launch options (GUI)
if ($Gui) {
    if (-not (Show-LauncherDialog)) { Write-Host 'Cancelled.'; exit 0 }
}

# ------------------------------------------------------- motion mode plumbing
$obsExe = @(
    "$env:ProgramFiles\obs-studio\bin\64bit\obs64.exe",
    "${env:ProgramFiles(x86)}\obs-studio\bin\64bit\obs64.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

switch ($Motion) {
    'camera' {
        # The Link 2C exposes no 4:3 modes, so PCSX2's direct 320x240 request
        # produces a stretched/cropped mess (verified 2026-07-02). Default to
        # the OBS Virtual Camera layer whenever OBS is installed; pass
        # -CameraName to force a direct device instead.
        if (-not $CameraName -and $obsExe) { $Obs = $true }
        $dev = if ($CameraName) { $CameraName }
               elseif ($Obs)    { 'OBS Virtual Camera' }
               else             { Get-IniValue $Ini 'USB1' 'webcam_device_name' }
        Write-Host "Motion: emulated Konami Capture Eye <- '$dev'"
        if (-not $DryRun) {
            Set-IniValue $Ini 'USB1' 'Type' 'webcam'
            Set-IniValue $Ini 'USB1' 'webcam_subtype' '1'
            Set-IniValue $Ini 'USB1' 'webcam_device_name' $dev
        }
        if ($Obs) {
            if (-not $obsExe) { throw 'OBS requested (-Obs) but obs64.exe not found. Install OBS Studio first.' }
            Write-Host "Starting OBS Virtual Camera ($obsExe)..."
            if (-not $DryRun) {
                if (Get-Process obs64 -ErrorAction SilentlyContinue) {
                    Write-Host 'OBS already running; using the existing instance (will leave it open on quit).'
                } else {
                    Clear-ObsCrashSentinels   # scrub any stale run_* so OBS won't force Safe Mode
                    Set-ObsCleanExit          # ConfirmOnExit=false -> we can close it cleanly on quit
                    # OBS must start from its own bin dir or it can't find its data files.
                    # No --minimize-to-tray: a taskbar window keeps a handle we can WM_CLOSE
                    # gracefully (tray-hidden has none), so we never have to hard-kill it.
                    $script:ObsProc = Start-Process -FilePath $obsExe -WorkingDirectory (Split-Path $obsExe) `
                        -WindowStyle Minimized -PassThru `
                        -ArgumentList '--startvirtualcam', '--disable-shutdown-check', `
                                      '--profile', 'Police247', '--collection', 'Police247'
                    $script:StartedObs = $true   # we own it -> close it when the game quits
                }
                # Gate the boot on OBS's virtual cam being live (not a blind sleep)
                Wait-ObsVirtualCam | Out-Null
            }
        }
    }
    'bridge' {
        Write-Host "Motion: Python head-tracking bridge ($BridgeSource) -> holds K (Square/cover)"
        if (-not $DryRun) {
            Set-IniValue $Ini 'USB1' 'Type' 'None'
            $argsList = @('"' + $Bridge + '"', '--source', $BridgeSource)
            Start-Process -FilePath 'python' -ArgumentList $argsList
            Start-Sleep -Seconds 2
        }
    }
    'none' {
        Write-Host 'Motion: none (duck manually with K; gun still active)'
        if (-not $DryRun) { Set-IniValue $Ini 'USB1' 'Type' 'None' }
    }
}

# ------------------------------------------------------------ phone gun helper
if ($Phone) { Start-GunHelper }

# ---------------------------------------------------------------- boot PCSX2
$pcsx2Args = @()
if (-not $NoFullscreen) { $pcsx2Args += '-fullscreen' }
$pcsx2Args += '--'
$pcsx2Args += '"' + $Game + '"'
Write-Host "Launching PCSX2: $Pcsx2 $($pcsx2Args -join ' ')"
if ($DryRun) {
    Write-Host 'Done (dry run). Good hunting, officer.'
    return
}

$pcsx2Proc = Start-Process -FilePath $Pcsx2 -ArgumentList $pcsx2Args `
    -WorkingDirectory (Split-Path $Pcsx2) -PassThru

# Wait for the game to exit, then tear down whatever this launcher started
# (OBS + the phone helper). try/finally so cleanup still runs on Ctrl-C.
try {
    if ($script:StartedObs -or $script:GunProc) {
        Write-Host 'Playing. Leave this window open — it closes OBS + the phone helper when you quit the game.'
    }
    if ($pcsx2Proc) { $pcsx2Proc.WaitForExit() }
}
finally {
    if ($script:GunProc) {
        Write-Host 'Stopping phone gun helper...'
        # /T kills the py.exe -> python.exe child tree, not just the launcher stub
        & taskkill.exe /PID $script:GunProc.Id /T /F 2>$null | Out-Null
    }
    if ($script:StartedObs) {
        Write-Host 'Closing OBS gracefully...'
        Stop-ObsGracefully -proc $script:ObsProc
    }
    Write-Host 'Done. Good hunting, officer.'
}
