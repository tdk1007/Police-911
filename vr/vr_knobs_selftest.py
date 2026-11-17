"""Builds and runs vr_knobs_selftest.cpp against the VRKnobs.h in pcsx2-knobs.patch (Earpiece
F-009), with MSVC from the VS Build Tools, without building PCSX2.

    py vr/vr_knobs_selftest.py

Takes the header straight out of the patch (git apply into a temp folder), so the test always
checks what the patch would put into the fork.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATCH = HERE / "pcsx2-knobs.patch"
TEST = HERE / "vr_knobs_selftest.cpp"
HEADER = "pcsx2/GS/VR/VRKnobs.h"
VSWHERE = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / \
    "Microsoft Visual Studio" / "Installer" / "vswhere.exe"


def vcvars():
    out = subprocess.run([str(VSWHERE), "-latest", "-products", "*", "-requires",
                          "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                          "-property", "installationPath"],
                         capture_output=True, text=True, check=True).stdout.strip()
    bat = Path(out.splitlines()[0]) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
    if not bat.is_file():
        sys.exit(f"no vcvars64.bat under {out}")
    return bat


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        subprocess.run(["git", "apply", f"--include={HEADER}", str(PATCH)], cwd=tmp, check=True)
        exe = tmp / "vr_knobs_selftest.exe"
        cmd = (f'call "{vcvars()}" >nul && cl /nologo /std:c++20 /EHsc /W4 /WX /O2 '
               f'/I "{tmp / "pcsx2"}" "{TEST}" /Fe"{exe}" /Fo"{tmp}\\\\"')
        build = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if build.returncode:
            print(build.stdout, build.stderr)
            sys.exit("build failed")
        return subprocess.run([str(exe)]).returncode


if __name__ == "__main__":
    sys.exit(main())
