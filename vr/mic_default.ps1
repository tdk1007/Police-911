# Show or set the Windows default recording device (for Claude Code /voice in VR).
#   .\mic_default.ps1                 # list capture devices, * = default
#   .\mic_default.ps1 -Set "Steam"    # make the first match the default (all roles)
#   add -Speakers to work on playback devices instead of recording devices
param([string]$Set = '', [switch]$Speakers)

Add-Type -Language CSharp @'
using System;
using System.Runtime.InteropServices;
using System.Collections.Generic;

[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceEnumerator {
    int EnumAudioEndpoints(int dataFlow, int stateMask, out IMMDeviceCollection devices);
    int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice device);
}
[Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceCollection {
    int GetCount(out int count);
    int Item(int index, out IMMDevice device);
}
[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDevice {
    int Activate(ref Guid iid, int ctx, IntPtr p, [MarshalAs(UnmanagedType.IUnknown)] out object o);
    int OpenPropertyStore(int access, out IPropertyStore store);
    int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);
}
[Guid("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IPropertyStore {
    int GetCount(out int c);
    int GetAt(int i, out PROPERTYKEY k);
    int GetValue(ref PROPERTYKEY k, out PROPVARIANT v);
}
[StructLayout(LayoutKind.Sequential)] struct PROPERTYKEY { public Guid fmtid; public int pid; }
[StructLayout(LayoutKind.Explicit)] struct PROPVARIANT { [FieldOffset(0)] public short vt; [FieldOffset(8)] public IntPtr p; }

[Guid("f8679f50-850a-41cf-9c72-430f290290c8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IPolicyConfig {
    int a(); int b(); int c(); int d(); int e(); int f(); int g(); int h(); int i(); int j();
    int SetDefaultEndpoint([MarshalAs(UnmanagedType.LPWStr)] string id, int role);
}
[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumeratorCom {}
[ComImport, Guid("870af99c-171d-4f9e-af0d-e63df40c2bc9")] class PolicyConfigCom {}

public static class Mic {
    static string Name(IMMDevice d) {
        IPropertyStore s; d.OpenPropertyStore(0, out s);
        var k = new PROPERTYKEY { fmtid = new Guid("a45c254e-df1c-4efd-8020-67d146a850e0"), pid = 14 };
        PROPVARIANT v; s.GetValue(ref k, out v);
        return Marshal.PtrToStringUni(v.p);
    }
    public static List<string[]> List(int flow) {
        var e = (IMMDeviceEnumerator)new MMDeviceEnumeratorCom();
        IMMDevice def; string defId = "";
        if (e.GetDefaultAudioEndpoint(flow, 0, out def) == 0) def.GetId(out defId);
        IMMDeviceCollection c; e.EnumAudioEndpoints(flow, 1, out c);
        int n; c.GetCount(out n);
        var r = new List<string[]>();
        for (int i = 0; i < n; i++) {
            IMMDevice d; c.Item(i, out d); string id; d.GetId(out id);
            r.Add(new[] { id == defId ? "*" : " ", Name(d), id });
        }
        return r;
    }
    public static void SetDefault(string id) {
        var p = (IPolicyConfig)new PolicyConfigCom();
        for (int role = 0; role < 3; role++) Marshal.ThrowExceptionForHR(p.SetDefaultEndpoint(id, role));
    }
}
'@

$flow = [int][bool]$Speakers -bxor 1   # 0 = render, 1 = capture
$devs = [Mic]::List($flow)
if ($Set) {
    $hit = $devs | Where-Object { $_[1] -like "*$Set*" } | Select-Object -First 1
    if (-not $hit) { Write-Error "No device matches '$Set'"; exit 1 }
    [Mic]::SetDefault($hit[2])
    Write-Host "Default device -> $($hit[1])"
    $devs = [Mic]::List($flow)
}
foreach ($d in $devs) { Write-Host "$($d[0]) $($d[1])" }
