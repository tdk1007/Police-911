# press.ps1 <keys> [repeat] -- send key(s) to the PCSX2 window.
#
#   .\press.ps1 Space          # Cross  (confirm / YES)
#   .\press.ps1 Return 2       # Start, twice
#   .\press.ps1 K              # Square (duck / cover)
#   .\press.ps1 Down; .\press.ps1 Up
#
# Keys are VIRTUAL-KEY NAMES, not SendKeys syntax. See $VK below.
#
# WHY NOT SendKeys: SendKeys delivers to whatever window currently has focus.
# Windows refuses foreground activation requested by a background process (it
# fails silently), so a SendKeys-based presser that "raises" PCSX2 and then
# types can end up typing into whatever the user was actually using -- a
# terminal, an editor. Unacceptable when running unattended.
#
# Instead we PostMessage WM_KEYDOWN/WM_KEYUP straight to the game's window
# handle. No focus required, and a key can only ever reach that window.
param(
    [string]$Keys = 'Space',
    [int]$Repeat = 1,
    [int]$DelayMs = 700,
    [switch]$List
)

$VK = @{
    'Space' = 0x20; 'Return' = 0x0D; 'Enter' = 0x0D; 'Escape' = 0x1B; 'Esc' = 0x1B
    'Up' = 0x26; 'Down' = 0x28; 'Left' = 0x25; 'Right' = 0x27
    'Tab' = 0x09; 'Back' = 0x08; 'Backspace' = 0x08
    'F1' = 0x70; 'F2' = 0x71; 'F3' = 0x72; 'F5' = 0x74; 'F6' = 0x75; 'F8' = 0x77
    '1' = 0x31; '2' = 0x32; '3' = 0x33
}
# Every letter, so a binding added in PCSX2.ini never silently has no key here.
# This table was missing 'T' -- which is Triangle, the only button on the last
# SENSOR ADJUSTMENT screen -- and the presser just reported "unknown key".
0x41..0x5A | ForEach-Object { $VK[[char]$_ -as [string]] = $_ }

# The game's bindings, for reference (PCSX2.ini [Pad1]):
#   Cross = Space   Square = K   Triangle = T   Circle = C
#   Start = Return  Select = Backspace   D-pad = arrows

if ($List) { $VK.Keys | Sort-Object | ForEach-Object { Write-Output $_ }; exit 0 }

Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public class K {
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr wp, IntPtr lp);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr h, EnumProc cb, IntPtr p);
  [DllImport("user32.dll")] public static extern int GetClassName(IntPtr h, StringBuilder s, int max);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  public delegate bool EnumProc(IntPtr h, IntPtr p);
  public static List<IntPtr> Children(IntPtr parent) {
    var found = new List<IntPtr>();
    EnumChildWindows(parent, delegate(IntPtr h, IntPtr p) {
      if (IsWindowVisible(h)) found.Add(h);
      return true;
    }, IntPtr.Zero);
    return found;
  }
  public static string ClassOf(IntPtr h) {
    var sb = new StringBuilder(256); GetClassName(h, sb, 256); return sb.ToString();
  }
}
"@

$WM_KEYDOWN = 0x0100; $WM_KEYUP = 0x0101

$p = Get-Process pcsx2* -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
if (-not $p) { Write-Host 'PCSX2 window not found'; exit 1 }

# PCSX2 renders into a child widget; depending on the renderer the keyboard
# focus window may be that child rather than the top-level frame. Post to the
# top-level AND to every visible child, which costs nothing and covers both.
$targets = @($p.MainWindowHandle) + [K]::Children($p.MainWindowHandle)

$names = $Keys -split '[,\s]+' | Where-Object { $_ }
foreach ($n in $names) {
    if (-not $VK.ContainsKey($n)) {
        Write-Host "unknown key '$n' -- run .\press.ps1 -List for the list"
        exit 2
    }
}

for ($i = 0; $i -lt $Repeat; $i++) {
    foreach ($n in $names) {
        $vk = [IntPtr]$VK[$n]
        foreach ($t in $targets) {
            [void][K]::PostMessage($t, $WM_KEYDOWN, $vk, [IntPtr]0)
        }
        Start-Sleep -Milliseconds 60
        foreach ($t in $targets) {
            [void][K]::PostMessage($t, $WM_KEYUP, $vk, [IntPtr]0)
        }
        Start-Sleep -Milliseconds $DelayMs
    }
}
Write-Output "sent '$Keys' x$Repeat to $($targets.Count) window(s) of '$($p.MainWindowTitle)'"
