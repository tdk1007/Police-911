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
  .\Play-Police247.ps1 -Vr                      # SteamVR: PINE + windowed + frame_bridge
  .\Play-Police247.ps1 -Immersive               # Stage 2: pcsx2-vr fork renders in the headset
  .\Play-Police247.ps1 -DryRun                  # show what would happen
#>
param(
    [ValidateSet('camera', 'synth', 'bridge', 'none')]
    [string]$Motion = 'camera',
    [string]$CameraName = '',           # DirectShow friendly name override
    [switch]$Obs,                       # use OBS Virtual Camera as the feed
    [ValidateSet('webcam', 'udp')]
    [string]$BridgeSource = 'webcam',
    [switch]$Phone,                     # iPhone-as-lightgun: start the UDP->mouse helper
    [switch]$Gui,                       # show a checkbox dialog before launching
    [switch]$Pine,                      # enable PCSX2's PINE IPC (memory tooling)
    [switch]$NoFullscreen,
    [switch]$Vr,                        # Steam Frame / SteamVR play (implies -Pine -NoFullscreen)
    [switch]$Immersive,                 # Stage 2: the pcsx2-vr fork as a SteamVR scene app (implies -Vr)
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
$Bridge = Join-Path $Root 'camera-tracking\bridge\police247_bridge.py'
$Pump   = Join-Path $Root 'camera-tracking\synth\pump.py'
$GunHelper = Join-Path $Root 'iPhone Gun\windows\gun_helper.py'
$PhonePref = Join-Path $Root '.launcher-phone.pref'   # remembers the checkbox state

# Track what WE launch so we can shut it down when the game quits
$script:StartedObs = $false
$script:ObsProc    = $null
$script:GunProc    = $null
$script:PumpProc   = $null
$script:BridgeProc = $null
$VrBridge = Join-Path $Root 'vr\frame_bridge.py'
$VrLog    = Join-Path $Root 'vr\bridge.log'

# Immersive VR: the pcsx2-vr fork (portable, own config) renders both eyes into the
# headset itself, so no Theater screen and no aim calibration.
if ($Immersive) {
    $Vr = $true
    $Pcsx2   = Join-Path $Root 'pcsx2-vr\bin\pcsx2-qtx64-avx2.exe'
    $Ini     = Join-Path $Root 'pcsx2-vr\bin\inis\PCSX2.ini'
    $BiosDir = Join-Path $Root 'pcsx2-vr\bin\bios'
}

# VR mode: the game must run windowed (SteamVR shows it on the Theater screen) and
# PINE must be on (frame_bridge writes lean/duck + aim into game RAM). Motion stays
# 'synth' unless asked otherwise: the game needs an emulated camera present to boot
# into play, and the bridge overrides what that camera reports anyway.
if ($Vr) {
    $Pine = $true
    $NoFullscreen = $true
    if (-not $PSBoundParameters.ContainsKey('Motion')) { $Motion = 'synth' }
}

# Steam game id of the "Police 24-7 (VR)" shortcut: (appid 4111256887 << 32) | 0x02000000
# (appid = crc32(exe + name) | 0x80000000, see vr\add_steam_shortcut.py).
$VrGameId = '17657713875153321984'

# SteamVR must already be up when Steam launches the game, or the game lands on the
# desktop instead of the Theater screen. So if it is down: start SteamVR, wait for
# it, then have Steam launch the shortcut again once this copy has exited (Steam
# ignores a launch request for a game it still thinks is running).
if ($Immersive -and -not $DryRun -and -not (Get-Process vrserver -ErrorAction SilentlyContinue)) {
    # The fork is its own SteamVR app: just make sure SteamVR is up before it boots.
    Write-Host 'SteamVR is not running - starting it. Put the Frame on / connect it to this PC.'
    Start-Process 'steam://rungameid/250820'
    $deadline = (Get-Date).AddMinutes(2)
    while (-not (Get-Process vrserver -ErrorAction SilentlyContinue)) {
        if ((Get-Date) -gt $deadline) {
            Write-Host 'SteamVR did not start within 2 minutes. Start it by hand, then launch again.' -ForegroundColor Red
            Start-Sleep -Seconds 8
            exit 1
        }
        Start-Sleep -Seconds 2
    }
    Start-Sleep -Seconds 8      # let the compositor settle
}
elseif ($Vr -and -not $Immersive -and -not $DryRun -and -not (Get-Process vrserver -ErrorAction SilentlyContinue)) {
    Write-Host 'SteamVR is not running - starting it. Put the Frame on / connect it to this PC.'
    Start-Process 'steam://rungameid/250820'
    $deadline = (Get-Date).AddMinutes(2)
    while (-not (Get-Process vrserver -ErrorAction SilentlyContinue)) {
        if ((Get-Date) -gt $deadline) {
            Write-Host 'SteamVR did not start within 2 minutes. Start it by hand, then launch the game again.' -ForegroundColor Red
            Start-Sleep -Seconds 8
            exit 1
        }
        Start-Sleep -Seconds 2
    }
    Write-Host 'SteamVR is up. Relaunching the game through Steam so it opens on the Theater screen...'
    Start-Sleep -Seconds 8      # let the compositor settle before a game asks for Theater
    # Ask again only once Steam has let go of this launch: a request that arrives
    # while Steam still counts the game as running gets stuck as a pending launch.
    # Steam counts EVERY process this one starts as part of the game (job object),
    # so the helper is created through WMI, outside that tree; a plain child would
    # itself keep the "game" alive until after it had already asked.
    $relaunch = "Wait-Process -Id $PID -ErrorAction SilentlyContinue; Start-Sleep -Seconds 5; " +
                "Start-Process 'steam://rungameid/$VrGameId'"
    $cmd = 'powershell.exe -NoProfile -WindowStyle Hidden -Command "' + $relaunch + '"'
    $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $cmd }
    if ($r.ReturnValue -ne 0) {
        Write-Host "Could not schedule the relaunch (WMI code $($r.ReturnValue)). Launch the game again from Steam." -ForegroundColor Red
        Start-Sleep -Seconds 8
    }
    exit 0
}

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

# ---------------------------------------------------------------------- PINE
# PCSX2's IPC server, used by camera-tracking\re\ram\* to read and write the
# running game's memory (the savestate sweep and the tracker-address hunt).
# Off by default: it opens a local TCP port, so only turn it on when asked.
if ($Pine) {
    Write-Host 'PINE: enabled on port 28011 (memory tooling can attach)'
    if (-not $DryRun) {
        Set-IniValue $Ini 'EmuCore' 'EnablePINE' 'true'
        Set-IniValue $Ini 'EmuCore' 'PINESlot' '28011'
    }
}

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
    'synth' {
        # Synthetic camera: pump.py draws an idealised target and pushes it
        # straight into the OBS Virtual Camera SINK via pyvirtualcam. OBS itself
        # must NOT run -- both want to own that sink, and whoever loses is
        # silently starved. So this mode deliberately never starts OBS.
        $dev = if ($CameraName) { $CameraName } else { 'OBS Virtual Camera' }
        Write-Host "Motion: synthetic camera (pump.py) -> emulated Capture Eye <- '$dev'"

        if (Get-Process obs64 -ErrorAction SilentlyContinue) {
            throw ("OBS is running, and it holds the same virtual-camera sink pump.py " +
                   "needs. Close OBS and retry, or use -Motion camera instead.")
        }
        if (-not (Test-Path -LiteralPath $Pump)) { throw "pump.py not found at $Pump" }

        if (-not $DryRun) {
            Set-IniValue $Ini 'USB1' 'Type' 'webcam'
            Set-IniValue $Ini 'USB1' 'webcam_subtype' '1'
            Set-IniValue $Ini 'USB1' 'webcam_device_name' $dev

            $py = Get-PythonCmd
            if (-not $py) { throw 'Synthetic camera needs Python, which was not found on PATH.' }
            Write-Host "Starting synthetic camera pump ($($py.Exe))..."
            $script:PumpProc = Start-Process -FilePath $py.Exe -PassThru `
                -WorkingDirectory (Split-Path $Pump) `
                -ArgumentList ($py.Args + @('"' + $Pump + '"'))
            # The pump must own the sink BEFORE PCSX2 opens the DirectShow filter;
            # if PCSX2 gets there first it captures a dead device and never recovers.
            Start-Sleep -Seconds 3
            if ($script:PumpProc.HasExited) {
                throw ("pump.py exited immediately (code $($script:PumpProc.ExitCode)). " +
                       "Usually a missing dependency: pip install -r " +
                       "camera-tracking\synth\requirements.txt")
            }
            Write-Host 'Synthetic camera pump is running.'
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

# ------------------------------------------------------------------ SteamVR
if ($Immersive) {
    # The fork's VR profile (see vr\IMMERSIVE.md): OpenVR output on D3D11, PAL vsync at
    # 90 Hz with the EE at 300% for two renders per vsync; the game-side patches that
    # use this are installed by frame_bridge --immersive.
    Write-Host 'Immersive VR: pcsx2-vr fork, D3D11, 90 Hz stereo'
    if (-not $DryRun) {
        Set-IniValue $Ini 'VR' 'Mode' 'openvr'
        # World scale for the IPD: 100 (the duck-depth guess) felt short in the headset
        # (2026-10-29); a hand-edited value in the ini is kept.
        if (-not (Get-IniValue $Ini 'VR' 'UnitsPerMetre')) { Set-IniValue $Ini 'VR' 'UnitsPerMetre' '130' }
        Set-IniValue $Ini 'EmuCore/GS' 'Renderer' '3'
        Set-IniValue $Ini 'EmuCore/GS' 'upscale_multiplier' '4'   # 2048x1792 per eye; 90 Hz holds (2026-10-21)
        Set-IniValue $Ini 'EmuCore/GS' 'FrameratePAL' '90'
        Set-IniValue $Ini 'EmuCore/GS' 'VsyncEnable' 'false'
        Set-IniValue $Ini 'EmuCore/GS' 'VsyncQueueSize' '0'      # EE at most one frame ahead of the GS: less head-pose latency
        Set-IniValue $Ini 'EmuCore/Speedhacks' 'EECycleRate' '3'
        # The fork's portable config starts with no hotkeys; PCSX2's usual F-key layout
        Set-IniValue $Ini 'Hotkeys' 'SaveStateToSlot' 'Keyboard/F1'
        Set-IniValue $Ini 'Hotkeys' 'NextSaveStateSlot' 'Keyboard/F2'
        Set-IniValue $Ini 'Hotkeys' 'LoadStateFromSlot' 'Keyboard/F3'
        Set-IniValue $Ini 'Hotkeys' 'OpenPauseMenu' 'Keyboard/Escape'
    }
}
elseif ($Vr) {
    if (-not (Test-Path -LiteralPath (Join-Path $Root 'vr\calib.json'))) {
        Write-Host 'No vr\calib.json yet: the bridge will run its aim calibration first.'
    }
}

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

# frame_bridge waits on PINE by itself until the game's code is loaded, so it can
# start right away. Its window stays minimised; the log is vr\bridge.log.
if ($Vr) {
    $py = Get-PythonCmd
    if (-not $py) { throw 'VR mode needs Python, which was not found on PATH.' }
    Write-Host "Starting VR bridge (log: $VrLog)..."
    $script:BridgeProc = Start-Process -FilePath 'cmd.exe' -PassThru -WindowStyle Minimized `
        -WorkingDirectory (Split-Path $VrBridge) `
        -ArgumentList ('/c ' + $py.Exe + ' ' + ($py.Args -join ' ') + ' -u "' + $VrBridge +
                       '" -v' + $(if ($Immersive) { ' --immersive' } else { '' }) +
                       ' > "' + $VrLog + '" 2>&1')
}

# Wait for the game to exit, then tear down whatever this launcher started
# (OBS + the phone helper). try/finally so cleanup still runs on Ctrl-C.
try {
    if ($script:BridgeProc) {
        Write-Host 'Playing in VR. Close the dashboard (system button) so the controllers reach the game.'
    }
    if ($script:StartedObs -or $script:GunProc) {
        Write-Host 'Playing. Leave this window open — it closes OBS + the phone helper when you quit the game.'
    }
    if ($pcsx2Proc) { $pcsx2Proc.WaitForExit() }
}
finally {
    if ($script:BridgeProc) {
        Write-Host 'Stopping VR bridge...'
        & taskkill.exe /PID $script:BridgeProc.Id /T /F 2>$null | Out-Null
    }
    if ($script:GunProc) {
        Write-Host 'Stopping phone gun helper...'
        # /T kills the py.exe -> python.exe child tree, not just the launcher stub
        & taskkill.exe /PID $script:GunProc.Id /T /F 2>$null | Out-Null
    }
    if ($script:PumpProc) {
        Write-Host 'Stopping synthetic camera pump...'
        # Safe to hard-kill: pyvirtualcam's OBS sink is a shared-memory surface
        # with no lock to orphan. This is NOT the case for obs64 itself, which
        # must always be closed gracefully or its virtual camera sticks until reboot.
        & taskkill.exe /PID $script:PumpProc.Id /T /F 2>$null | Out-Null
    }
    if ($script:StartedObs) {
        Write-Host 'Closing OBS gracefully...'
        Stop-ObsGracefully -proc $script:ObsProc
    }
    Write-Host 'Done. Good hunting, officer.'
}
