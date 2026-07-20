<#
.SYNOPSIS
  Point the Police 24/7 rig at ANY webcam — generates the OBS profile and
  4:3 "EyeToy" scene for the camera you pick.

.DESCRIPTION
  PCSX2's emulated Konami Capture Eye requests 320x240 (4:3) over DirectShow.
  Most modern webcams are 16:9-only, which comes back stretched/cropped. The
  rig therefore routes every camera through OBS's Virtual Camera on a 640x480
  4:3 canvas with a center-cut crop — which works for ANY resolution/aspect,
  because the scene item uses bounds-based outer scaling.

  This script:
    1. Lists physical cameras (virtual cams are excluded).
    2. Writes the OBS profile "Police247" (640x480@30) and scene collection
       "Police247" (scene "EyeToy" = your camera, center-cut to 4:3).
    3. Safe to re-run any time you change cameras.

  Run it BEFORE first launching the game, and close OBS first if it's open.

.EXAMPLES
  .\Setup-Camera.ps1                 # interactive picker
  .\Setup-Camera.ps1 -DeviceIndex 0  # non-interactive
  .\Setup-Camera.ps1 -List           # just list cameras
#>
param(
    [int]$DeviceIndex = -1,
    [switch]$List
)
$ErrorActionPreference = 'Stop'

# --------------------------------------------------------------- enumerate
# Physical cameras enumerate under PNPClass Camera/Image with a USB instance
# ID. Virtual cameras (OBS, NVIDIA Broadcast...) are ROOT-enumerated — skip.
$cams = @(Get-CimInstance Win32_PnPEntity | Where-Object {
    $_.PNPClass -in @('Camera', 'Image') -and $_.DeviceID -like 'USB\*'
})
if ($cams.Count -eq 0) {
    Write-Host 'No physical USB camera is currently connected.' -ForegroundColor Red
    Write-Host 'Plug the camera into the port you will actually use (the OBS'
    Write-Host 'device id encodes the USB port — moving ports needs a re-run),'
    Write-Host 'wait for Windows to install it, then run this script again.'
    exit 1
}
Write-Host 'Physical cameras:'
for ($i = 0; $i -lt $cams.Count; $i++) {
    Write-Host ("  [{0}] {1}" -f $i, $cams[$i].Name)
}
if ($List) { exit 0 }

if ($DeviceIndex -lt 0) {
    $DeviceIndex = [int](Read-Host 'Pick a camera number')
}
if ($DeviceIndex -ge $cams.Count) { throw "No camera #$DeviceIndex" }
$cam = $cams[$DeviceIndex]

# DirectShow moniker device path: \\?\<instance-id with # separators, lower
# case>#{KSCATEGORY_CAPTURE}\global — the format OBS stores in
# video_device_id ("<FriendlyName>:<DevicePath>").
$devPath = '\\?\' + ($cam.DeviceID -replace '\\', '#').ToLower() +
           '#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global'
$videoDeviceId = "$($cam.Name):$devPath"
Write-Host "Using: $($cam.Name)"
Write-Host "  device id: $videoDeviceId"

# ------------------------------------------------------------------- write
$obsDir = Join-Path $env:APPDATA 'obs-studio'
if (Get-Process obs64 -ErrorAction SilentlyContinue) {
    throw 'OBS is running — close it first, then re-run this script.'
}
New-Item -ItemType Directory -Force "$obsDir\basic\profiles\Police247", "$obsDir\basic\scenes" | Out-Null

@"
[General]
Name=Police247
[Video]
BaseCX=640
BaseCY=480
OutputCX=640
OutputCY=480
FPSType=0
FPSCommon=30
"@ | Set-Content "$obsDir\basic\profiles\Police247\basic.ini" -Encoding utf8

# Scene collection: template with the chosen device spliced in. The scene
# item scales the source to COVER the 4:3 canvas (bounds_type 3 =
# OBS_BOUNDS_SCALE_OUTER) so any aspect ratio center-cuts cleanly.
# NOT bounds_type 2 (OBS_BOUNDS_SCALE_INNER): that FITS the source inside the
# canvas, which letterboxes a 16:9 camera into 30px black bars top and bottom.
$scene = @'
{
    "current_program_scene": "EyeToy",
    "current_scene": "EyeToy",
    "current_transition": "Fade",
    "groups": [],
    "modules": {},
    "name": "Police247",
    "preview_locked": false,
    "quick_transitions": [],
    "saved_projectors": [],
    "scaling_enabled": false,
    "scene_order": [ { "name": "EyeToy" } ],
    "transition_duration": 300,
    "transitions": [],
    "sources": [
        {
            "enabled": true, "flags": 0, "hotkeys": {}, "id": "scene",
            "mixers": 0, "monitoring_type": 0, "muted": false,
            "name": "EyeToy", "private_settings": {},
            "settings": {
                "custom_size": false,
                "id_counter": 1,
                "items": [
                    {
                        "align": 5, "blend_method": "default", "blend_type": "normal",
                        "bounds": { "x": 640.0, "y": 480.0 },
                        "bounds_align": 0, "bounds_type": 3,
                        "crop_bottom": 0, "crop_left": 0, "crop_right": 0, "crop_top": 0,
                        "group_item_backup": false,
                        "hide_transition": { "duration": 0 },
                        "id": 1, "locked": false,
                        "name": "GameCamera",
                        "pos": { "x": 0.0, "y": 0.0 },
                        "private_settings": {}, "rot": 0.0,
                        "scale": { "x": 1.0, "y": 1.0 },
                        "scale_filter": "disable",
                        "show_transition": { "duration": 0 },
                        "source_uuid": "9c7b3f2e-5a41-4c8e-b0d6-1f2a3b4c5d6e",
                        "visible": true
                    }
                ]
            },
            "sync": 0, "uuid": "1a2b3c4d-0001-4000-8000-000000000001",
            "versioned_id": "scene", "volume": 1.0, "balance": 0.5,
            "deinterlace_field_order": 0, "deinterlace_mode": 0,
            "push-to-mute": false, "push-to-mute-delay": 0,
            "push-to-talk": false, "push-to-talk-delay": 0
        },
        {
            "enabled": true, "flags": 0, "hotkeys": {}, "id": "dshow_input",
            "mixers": 255, "monitoring_type": 0, "muted": true,
            "name": "GameCamera", "private_settings": {},
            "settings": {
                "active": true,
                "autorotation": true,
                "buffering": false,
                "deactivate_when_not_showing": false,
                "hw_decode": false,
                "res_type": 0,
                "video_device_id": "__VIDEO_DEVICE_ID__"
            },
            "sync": 0, "uuid": "9c7b3f2e-5a41-4c8e-b0d6-1f2a3b4c5d6e",
            "versioned_id": "dshow_input", "volume": 1.0, "balance": 0.5,
            "deinterlace_field_order": 0, "deinterlace_mode": 0,
            "push-to-mute": false, "push-to-mute-delay": 0,
            "push-to-talk": false, "push-to-talk-delay": 0
        }
    ]
}
'@
# JSON-escape backslashes in the device id
$scene = $scene.Replace('__VIDEO_DEVICE_ID__', $videoDeviceId.Replace('\', '\\'))
Set-Content "$obsDir\basic\scenes\Police247.json" -Value $scene -Encoding utf8

# make Police247 the active profile/collection on next OBS start
$globalIni = "$obsDir\global.ini"
if (-not (Test-Path $globalIni)) {
@"
[General]
FirstRun=true
EnableAutoUpdates=false
[Basic]
Profile=Police247
ProfileDir=Police247
SceneCollection=Police247
SceneCollectionFile=Police247
"@ | Set-Content $globalIni -Encoding utf8
    Copy-Item $globalIni "$obsDir\user.ini" -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Host 'Done. OBS profile "Police247" + scene "EyeToy" written for:' -ForegroundColor Green
Write-Host "  $($cam.Name)"
Write-Host 'The launcher starts OBS with this scene automatically.'
