# Screenshot the PCSX2 CLIENT area -> pcsx2_shot.png next to this script,
# plus pcsx2_shot.json describing where it came from.
#
# Client area, not window rect: the window rect includes the title bar and
# borders, whose thickness changes with theme, DPI and maximised state. Anything
# downstream that wants to say "the calibration ring is 62% across the picture"
# needs the picture to be exactly the rendered frame and nothing else.
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class W {
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after,
      int x, int y, int cx, int cy, uint flags);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public struct RECT { public int L, T, R, B; }
  public struct POINT { public int X, Y; }
}
"@

# MUST come before any window query or capture. Without it Windows virtualises
# coordinates for this DPI-unaware process: on a 150%-scaled display the client
# origin came back as (2035,363) when the window was physically at (3053,545),
# so the capture grabbed a rectangle of desktop 1000 px away from the game and
# the oracle "read" the wallpaper. CopyFromScreen works in physical pixels, so
# the query has to as well.
[void][W]::SetProcessDPIAware()
$p = Get-Process pcsx2* -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
if (-not $p) { Write-Host "PCSX2 window not found"; exit 1 }

# CopyFromScreen reads the physical screen, so anything stacked on top of PCSX2
# lands in the shot instead of the game. PrintWindow would capture an occluded
# window without disturbing anything, but PCSX2 renders through a
# hardware-accelerated swapchain and PrintWindow returns black for those.
#
# SetForegroundWindow alone is not enough: Windows refuses foreground activation
# requested by a process that does not already own the foreground, and fails
# silently. SetWindowPos(HWND_TOPMOST) needs no such rights, so raise the window
# that way, capture, then drop it back out of topmost.
$HWND_TOPMOST = [IntPtr](-1); $HWND_NOTOPMOST = [IntPtr](-2)
$SWP = 0x0001 -bor 0x0002 -bor 0x0040          # NOSIZE | NOMOVE | SHOWWINDOW
[void][W]::ShowWindow($p.MainWindowHandle, 9)  # SW_RESTORE, in case minimised
[void][W]::SetWindowPos($p.MainWindowHandle, $HWND_TOPMOST, 0, 0, 0, 0, $SWP)
[void][W]::SetForegroundWindow($p.MainWindowHandle)   # for keyboard input; may fail, fine
Start-Sleep -Milliseconds 300

$rc = New-Object W+RECT
[void][W]::GetClientRect($p.MainWindowHandle, [ref]$rc)
$origin = New-Object W+POINT
$origin.X = 0; $origin.Y = 0
[void][W]::ClientToScreen($p.MainWindowHandle, [ref]$origin)

$w = $rc.R - $rc.L; $h = $rc.B - $rc.T
if ($w -le 0 -or $h -le 0) { Write-Host "PCSX2 client area is empty (minimised?)"; exit 1 }

$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($origin.X, $origin.Y, 0, 0, (New-Object System.Drawing.Size $w, $h))
$out = Join-Path $PSScriptRoot 'pcsx2_shot.png'
$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()

# Drop back out of topmost so the game window does not sit permanently above
# everything else on the user's desktop.
[void][W]::SetWindowPos($p.MainWindowHandle, $HWND_NOTOPMOST, 0, 0, 0, 0, $SWP)

$meta = [ordered]@{
    left   = $origin.X
    top    = $origin.Y
    width  = $w
    height = $h
    title  = $p.MainWindowTitle
    taken  = (Get-Date).ToString('o')
}
$json = $meta | ConvertTo-Json -Compress
[System.IO.File]::WriteAllText((Join-Path $PSScriptRoot 'pcsx2_shot.json'), $json)
Write-Output $json
