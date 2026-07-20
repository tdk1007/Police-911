# press.ps1 <keys> [repeat] -- focus the PCSX2 window and send key(s).
# Uses SendKeys syntax: " " = Space (Cross), "{ENTER}" = Start, "k" = Square.
param([string]$Keys = " ", [int]$Repeat = 1, [int]$DelayMs = 700)

Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Fg { [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); }
"@

$p = Get-Process pcsx2* -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
if (-not $p) { Write-Host "PCSX2 window not found"; exit 1 }

[void][Fg]::SetForegroundWindow($p.MainWindowHandle)
Start-Sleep -Milliseconds 500
for ($i = 0; $i -lt $Repeat; $i++) {
    [System.Windows.Forms.SendKeys]::SendWait($Keys)
    Start-Sleep -Milliseconds $DelayMs
}
Write-Host "sent '$Keys' x$Repeat to '$($p.MainWindowTitle)'"
