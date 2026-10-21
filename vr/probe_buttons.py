"""Log the bridge's SteamVR input actions (fire / recenter / talk) for N seconds.

    py probe_buttons.py [seconds]

Uses the action manifest in input/actions.json -- the same path frame_bridge
uses -- so it shows exactly what the bridge would see.
"""
import os, sys, time, openvr

HERE = os.path.dirname(os.path.abspath(__file__))
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 90
openvr.init(openvr.VRApplication_Overlay)
inp = openvr.VRInput()
inp.setActionManifestPath(os.path.join(HERE, 'input', 'actions.json'))
aset = inp.getActionSetHandle('/actions/bridge')
fire, rec, talk = (inp.getActionHandle(f'/actions/bridge/in/{n}') for n in ('fire', 'recenter', 'talk'))
sets = (openvr.VRActiveActionSet_t * 1)()
sets[0].ulActionSet = aset
# global-overlay priority: receive input even while another app (desktop view) has focus
sets[0].nPriority = openvr.k_nActionSetOverlayGlobalPriorityMin
last = None
t0 = time.time()
print(f'probing {secs:.0f}s', flush=True)
while time.time() - t0 < secs:
    inp.updateActionState(sets)
    f = inp.getAnalogActionData(fire, openvr.k_ulInvalidInputValueHandle)
    r = inp.getDigitalActionData(rec, openvr.k_ulInvalidInputValueHandle)
    k = inp.getDigitalActionData(talk, openvr.k_ulInvalidInputValueHandle)
    cur = (f.bActive, round(f.x, 1), r.bActive, r.bState, k.bActive, k.bState)
    if cur != last:
        last = cur
        print(f'{time.time()-t0:5.1f} fire(active={f.bActive}) {f.x:.2f}  '
              f'recenter(active={r.bActive}) {r.bState}  talk(active={k.bActive}) {k.bState}',
              flush=True)
    time.sleep(0.02)
openvr.shutdown()
print('done', flush=True)
