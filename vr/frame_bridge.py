"""Steam Frame (or any SteamVR headset) -> Police 24/7 in PCSX2.

Stage 1 "flatscreen VR": PCSX2 is shown on a virtual screen (SteamVR desktop /
theatre view). Then:
    headset position vs. a calibrated neutral  -> lean / duck   (head_writer)
    right controller pointing at the picture   -> crosshair     (aim_writer, RAM write)
    right trigger                              -> fire          (real left click)
    left controller held at the mouth ("radio mic") -> Claude Code /voice push-to-talk
                                                  (voice_ptt: focuses the terminal,
                                                  holds Space, gives focus back)

    py frame_bridge.py --calibrate     # once per setup: neutral stance + 4 corners
    py frame_bridge.py                 # play
    py frame_bridge.py --dry           # no PINE / no clicks; print what would be sent
    py frame_bridge.py --voice-only    # just the left-hand push-to-talk, no game
    py frame_bridge.py --immersive     # Stage 2: pcsx2-vr fork renders in the headset

Aim calibration: the right controller's aim ("tip") ray is intersected with a
plane SCREEN_M in front of the calibrated stance, and a homography maps those hit
points to the picture's 0..1 coordinates from the 4 corners you point at. Exact
from the calibration spot whatever the true distance; while you lean it stays on
target as far as SCREEN_M matches the real screen distance.

Recenter in play: hold the right GRIP for 1.5 s while standing neutral.

Buttons come from SteamVR input actions (input/actions.json), which SteamVR
withholds while the dashboard is open: launch the game from Steam ("Police 24-7
(VR)", see add_steam_shortcut.py) so it plays on the Theater screen.
"""
import argparse, json, math, os, sys, time

import numpy as np
import openvr

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, '..', 'camera-tracking', 'pose'),
                os.path.join(HERE, '..', 'camera-tracking', 're', 'ram')]
CALIB = os.path.join(HERE, 'calib.json')

LEAN_M = 0.40        # metres of sideways neck travel for a full lean
SCREEN_M = 3.0       # assumed distance to the theater screen (SteamVR defaultTheaterDistance)
DUCK_M = 0.22        # metres of neck drop for a full duck
NECK = np.array([0.0, -0.10, 0.08])  # neck pivot in the HMD frame (below, behind the eyes):
                                     # head tilts/nods swing the eyes, not this point
TRIG_ON, TRIG_OFF = 0.60, 0.40
MOUTH = np.array([0.0, -0.08, -0.08])   # mouth in the HMD frame (below, in front)
MIC_ON_M, MIC_OFF_M = 0.15, 0.25         # left controller this close = talking
MIC_DWELL_S = 0.3                        # hold it there this long to start
RECENTER_S = 1.5
HZ = 90


def beep(f=1000, ms=120):
    try:
        import winsound
        winsound.Beep(f, ms)
    except Exception:
        pass


def mat(m34):
    """HmdMatrix34_t -> (R 3x3, t 3)."""
    a = np.array([[m34.m[i][j] for j in range(4)] for i in range(3)], dtype=np.float64)
    return a[:, :3], a[:, 3]


def yaw_of(R):
    """Heading of a pose's forward (-Z) projected on the floor."""
    f = -R[:, 2]
    return math.atan2(-f[0], -f[2])


def yaw_rot(yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


class VR:
    """Poses from IVRSystem; buttons from IVRInput (input/actions.json).

    Legacy getControllerState returns nothing to an overlay/background app, so
    the trigger, grip and push-to-talk buttons come from an action set with
    global-overlay priority (needs the SteamVR setting
    steamvr/globalActionSetPriority = true). Even then SteamVR delivers no
    buttons while the dashboard is open -- launch the game from Steam
    ("Police 24-7 (VR)") so it shows on the Theater screen with the dashboard
    hidden. Poses always flow, so the radio-mic gesture works either way.
    """
    def __init__(self):
        openvr.init(openvr.VRApplication_Overlay)
        self.sys = openvr.VRSystem()
        self.inp = openvr.VRInput()
        self.inp.setActionManifestPath(os.path.join(HERE, 'input', 'actions.json'))
        act = lambda n: self.inp.getActionHandle(f'/actions/bridge/{n}')
        self.a_fire, self.a_recenter, self.a_talk = act('in/fire'), act('in/recenter'), act('in/talk')
        self.a_haptic, self.a_aim = act('out/haptic'), act('in/aim')
        self.sets = (openvr.VRActiveActionSet_t * 1)()
        self.sets[0].ulActionSet = self.inp.getActionSetHandle('/actions/bridge')
        self.sets[0].nPriority = openvr.k_nActionSetOverlayGlobalPriorityMin
        self._mic_since = None

    def poses(self):
        self.inp.updateActionState(self.sets)
        return self.sys.getDeviceToAbsoluteTrackingPose(
            openvr.TrackingUniverseStanding, 0, openvr.k_unMaxTrackedDeviceCount)

    def hmd(self, poses):
        p = poses[openvr.k_unTrackedDeviceIndex_Hmd]
        return mat(p.mDeviceToAbsoluteTracking) if p.bPoseIsValid else None

    def right(self):
        return self.sys.getTrackedDeviceIndexForControllerRole(
            openvr.TrackedControllerRole_RightHand)

    def left(self):
        return self.sys.getTrackedDeviceIndexForControllerRole(
            openvr.TrackedControllerRole_LeftHand)

    def _digital(self, a):
        d = self.inp.getDigitalActionData(a, openvr.k_ulInvalidInputValueHandle)
        return bool(d.bState) if d.bActive else None

    def mouth_dist(self, poses):
        """Metres from the left controller to the mouth (a point below/in front of
        the eyes)."""
        li = self.left()
        if li == openvr.k_unTrackedDeviceIndexInvalid:
            return None
        h, c = poses[openvr.k_unTrackedDeviceIndex_Hmd], poses[li]
        if not (h.bPoseIsValid and c.bPoseIsValid):
            return None
        Rh, th = mat(h.mDeviceToAbsoluteTracking)
        _, tc = mat(c.mDeviceToAbsoluteTracking)
        return float(np.linalg.norm(tc - (th + Rh @ MOUTH)))

    def talk(self, held=False):
        """Push-to-talk: the radio-mic gesture (left controller held at the mouth)
        or the talk button (left d-pad down / right A). `held` adds hysteresis so
        wobble doesn't cut the recording."""
        if self._digital(self.a_talk):
            return True
        d = self.mouth_dist(self.poses())
        if d is not None and d < (MIC_OFF_M if held else MIC_ON_M):
            self._mic_since = self._mic_since or time.time()
            return held or time.time() - self._mic_since > MIC_DWELL_S
        self._mic_since = None
        return False

    def buzz(self, ms=30):
        try:
            self.inp.triggerHapticVibrationAction(self.a_haptic, 0, ms / 1000, 160, 0.6,
                                                  openvr.k_ulInvalidInputValueHandle)
        except openvr.OpenVRError:
            pass

    def controller(self, poses, idx):
        """(pose, {'trigger', 'grip'}) for a controller; buttons are None while
        SteamVR withholds input (dashboard open)."""
        if idx == openvr.k_unTrackedDeviceIndexInvalid:
            return None, None
        p = poses[idx]
        pose = mat(p.mDeviceToAbsoluteTracking) if p.bPoseIsValid else None
        if idx == self.right():            # the gun: use SteamVR's aim ("tip") pose
            a = self.inp.getPoseActionDataRelativeToNow(
                self.a_aim, openvr.TrackingUniverseStanding, 0,
                openvr.k_ulInvalidInputValueHandle)
            if a.bActive and a.pose.bPoseIsValid:
                pose = mat(a.pose.mDeviceToAbsoluteTracking)
        f = self.inp.getAnalogActionData(self.a_fire, openvr.k_ulInvalidInputValueHandle)
        if not f.bActive:
            return pose, None
        return pose, {'trigger': f.x, 'grip': bool(self._digital(self.a_recenter))}

    def shutdown(self):
        openvr.shutdown()


def pointing(pose, t0, yaw0):
    """Aim ray -> (x, y) where it hits the screen plane, in metres, in the
    neutral-facing frame centred on the calibrated head position. The plane is
    taken as SCREEN_M in front of the player (SteamVR's theater default), so the
    hit point -- unlike the pointing angle -- stays put while you lean."""
    R, t = pose
    Rn = yaw_rot(yaw0).T
    o, d = Rn @ (t - t0), Rn @ (-R[:, 2])
    if d[2] > -1e-3:                     # pointing backwards: no intersection
        return None
    s = (-SCREEN_M - o[2]) / d[2]
    return np.array([o[0] + s * d[0], o[1] + s * d[1]])


def head_offsets(hmd, t0, yaw0):
    """Neck-point displacement from the calibrated stance -> (lean, duck)."""
    R, t = hmd
    Ry = yaw_rot(yaw0)
    o = Ry.T @ ((t + R @ NECK) - (t0 + Ry @ NECK))   # calibrated upright, facing yaw0
    return o[0] / LEAN_M, -o[1] / DUCK_M          # +x = right, drop = duck


def wait_trigger(vr, what, tone):
    """Block until the right trigger is pulled and released; return samples
    collected while it was held."""
    print(f'  -> {what}, then pull the RIGHT TRIGGER', flush=True)
    beep(tone)
    held, samples = False, []
    while True:
        poses = vr.poses()
        pose, st = vr.controller(poses, vr.right())
        hmd = vr.hmd(poses)
        if st:
            if not held and st['trigger'] > TRIG_ON:
                held = True
            if held:
                samples.append((hmd, pose))
                if st['trigger'] < TRIG_OFF:
                    beep(1500, 60)
                    return samples
        time.sleep(1 / HZ)


def calibrate(vr):
    print('CALIBRATION -- put the headset on, PCSX2 visible on the virtual screen.')
    s = wait_trigger(vr, 'Stand where you will play, upright and centred, look at the screen',
                     800)
    hm = [h for h, _ in s if h is not None]
    if not hm:
        raise SystemExit('headset pose was not valid -- is it tracking?')
    t0 = np.mean([h[1] for h in hm], axis=0)
    yaw0 = float(np.mean([yaw_of(h[0]) for h in hm]))
    corners = []
    for name in ('TOP-LEFT', 'TOP-RIGHT', 'BOTTOM-RIGHT', 'BOTTOM-LEFT'):
        s = wait_trigger(vr, f'Point at the {name} corner of the GAME PICTURE', 1000)
        pts = [pointing(c, t0, yaw0) for _, c in s if c is not None]
        pts = [q for q in pts if q is not None]
        if not pts:
            raise SystemExit(f'no valid controller pose for {name}')
        corners.append(np.mean(pts, axis=0).tolist())
    cal = {'t0': t0.tolist(), 'yaw0': yaw0, 'corners': corners, 'model': 'plane',
           'screen_m': SCREEN_M, 'when': time.ctime()}
    with open(CALIB, 'w') as f:
        json.dump(cal, f, indent=1)
    beep(600); beep(900)
    print(f'saved {CALIB}')
    return cal


def homography(corners):
    import cv2
    src = np.array(corners, dtype=np.float32)
    dst = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)
    return cv2.getPerspectiveTransform(src, dst)


def apply_h(Hm, q):
    v = Hm @ np.array([q[0], q[1], 1.0])
    return v[0] / v[2], v[1] / v[2]


class _DryPine:
    def write32(self, a, v):
        pass

    def read32(self, a):
        return 0


def voice_tick(vr, ptt):
    talk = vr.talk(ptt.held)
    if talk != ptt.held:
        vr.buzz(40 if talk else 15)
        beep(1000, 80) if talk else beep(500, 80)
        ptt.update(talk)
        print('voice: listening' if ptt.held else 'voice: sent', flush=True)


def voice_only(vr, ptt):
    print('push-to-talk running -- hold the LEFT controller at your mouth to talk, '
          'lower it to send. Ctrl+C to stop.', flush=True)
    try:
        while True:
            voice_tick(vr, ptt)
            time.sleep(1 / HZ)
    except KeyboardInterrupt:
        pass
    finally:
        ptt.release()


def wait_for_game(P, timeout=240):
    """Connect to PINE once the game's code is in RAM (the launcher starts the bridge
    together with PCSX2, so PINE may not be up yet, or may still be in the BIOS)."""
    import hook
    want = (hook.GUARD_ORIGINAL, (hook.NOP, hook.NOP))
    end = time.time() + timeout
    said = False
    while True:
        p = P.Pine(timeout=3.0)
        try:
            p.connect()
            if (p.status() == P.STATUS_RUNNING
                    and tuple(p.read32(a) for a in hook.GUARDS) in want):
                p.sock.settimeout(15.0)
                return p
        except (OSError, P.PineError):
            pass
        p.close()
        if time.time() > end:
            raise SystemExit('the game never came up on PINE (is PCSX2 running with -Pine?)')
        if not said:
            print('waiting for PCSX2 to boot the game...', flush=True)
            said = True
        time.sleep(2)


def run(vr, cal, dry=False, verbose=False, ptt=None):
    t0, yaw0 = np.array(cal['t0']), cal['yaw0']
    if cal.get('model') != 'plane':
        raise SystemExit('calib.json is from the old angle model -- run --calibrate again')
    Hm = homography(cal['corners'])
    if dry:
        head = aim = None
        p = None
    else:
        import pine as P
        from head_writer import HeadWriter
        from aim_writer import AimWriter
        p = wait_for_game(P)
        head, aim = HeadWriter(p), AimWriter(p)
    print('bridge running -- Ctrl+C to stop. Hold right GRIP 1.5 s to recenter.', flush=True)
    firing = False
    grip_since = None
    last_print = 0
    try:
        while True:
            poses = vr.poses()
            hmd = vr.hmd(poses)
            pose, st = vr.controller(poses, vr.right())

            dx = dy = None
            if hmd is not None:
                dx, dy = head_offsets(hmd, t0, yaw0)
                if head:
                    head.set(dx, dy)

            u = v = None
            if pose is not None:
                q = pointing(pose, t0, yaw0)
                if q is not None:
                    u, v = apply_h(Hm, q)
                    u, v = min(max(u, 0.0), 1.0), min(max(v, 0.0), 1.0)

            if st:
                if not firing and st['trigger'] > TRIG_ON:
                    firing = True
                elif firing and st['trigger'] < TRIG_OFF:
                    firing = False
                if st['grip']:
                    grip_since = grip_since or time.time()
                    if time.time() - grip_since > RECENTER_S and hmd is not None:
                        t0, yaw0 = hmd[1].copy(), yaw_of(hmd[0])
                        cal['t0'], cal['yaw0'] = t0.tolist(), yaw0
                        with open(CALIB, 'w') as f:
                            json.dump(cal, f, indent=1)
                        beep(600); beep(900)
                        grip_since = float('inf')          # once per hold
                else:
                    grip_since = None
            if ptt:
                voice_tick(vr, ptt)
            if aim:
                aim.set(u, v, firing if st else None)

            if verbose or dry:
                now = time.time()
                if now - last_print > 0.25:
                    last_print = now
                    hs = f'lean={dx:+.2f} duck={dy:+.2f}' if dx is not None else 'hmd=?'
                    a = f'aim=({u:.2f},{v:.2f})' if u is not None else 'aim=?'
                    t = f"trig={st['trigger']:.2f}{' FIRE' if firing else ''}" if st else 'trig=?'
                    print(f'{hs}  {a}  {t}', flush=True)
            time.sleep(1 / HZ)
    except KeyboardInterrupt:
        pass
    finally:
        if ptt:
            ptt.release()
        if aim:
            aim.release()
            if aim.blocked:
                print(f'note: {aim.blocked} trigger pulls ignored because PCSX2 was not '
                      f'the foreground window')
        if head:
            head.neutral()
        if p:
            p.close()


# --- Stage 2: immersive (pcsx2-vr fork, [VR] Mode = openvr) ------------------------
AIM_DIST_M = 6.0     # the gun ray is aimed at the point this far along it
STOCK_TAN = (0.635, 0.443)   # stock frame half-extents (tan), measured 2026-10-21
S_RECENTER = 0x48            # vrcam slot the fork watches: nonzero = re-zero head yaw


def aim_target(hmd, gun, yaw0):
    """The point AIM_DIST_M along the gun's aim ray, relative to the head, in (head
    frame, neutral-facing frame). The neutral-facing frame is the game camera's."""
    (Rh, th), (Rg, tg) = hmd, gun
    p = tg + AIM_DIST_M * (-Rg[:, 2]) - th
    return Rh.T @ p, yaw_rot(yaw0).T @ p


def project_aim(hmd, gun, yaw0, render_tan, frame='render'):
    """Gun ray -> crosshair (u, v) in 0..1 of the game picture.

    'render' projects through the head-rotated render camera (where the player sees
    the target, so the green ring sits on it); 'logic' through the game's unrotated
    camera (head yaw ignored)."""
    q_head, q_game = aim_target(hmd, gun, yaw0)
    q = q_head if frame == 'render' else q_game
    if q[2] > -1e-3:
        return None
    x, y = q[0] / -q[2], q[1] / -q[2]                # tangents, +y up
    u = 0.5 + 0.5 * x / render_tan[0]
    v = 0.5 - 0.5 * y / render_tan[1]
    return min(max(u, 0.0), 1.0), min(max(v, 0.0), 1.0)


class Patches:
    """Keeps the game-side VR patches (vrcam + vr90 stereo) installed. A savestate load
    or a reset restores the original code, so this re-checks once a second."""
    def __init__(self, p, hz=90):
        import vrcam, vr90, vrshot
        self.p, self.hz, self.vrcam, self.vr90, self.vrshot = p, hz, vrcam, vr90, vrshot
        self.next = 0.0
        self.render_tan = STOCK_TAN

    def tick(self):
        if time.time() < self.next:
            return
        self.next = time.time() + 1.0
        try:
            if (self.vrcam.state(self.p) != 'on' or self.vr90.state(self.p) != 'on'
                    or self.vrshot.state(self.p) != 'on'):
                self.vrcam.enable(self.p)
                self.vr90.enable(self.p, self.hz, stereo=True)
                self.vrshot.enable(self.p)
                print('VR patches installed (vrcam + vr90 stereo + vrshot)', flush=True)
            st = self.vrcam.read_status(self.p)       # FOV as the fork set it
            if st['fov_scale_h'] and st['fov_scale_v']:
                self.render_tan = (STOCK_TAN[0] * st['fov_scale_h'], STOCK_TAN[1] * st['fov_scale_v'])
        except RuntimeError as e:                     # code is neither stock nor patched
            print(f'VR patches: {e}', flush=True)

    def recenter(self):
        self.p.write32(self.vrcam.SLOTS + S_RECENTER, 1)

    def shot(self, q_game):
        """Where a shot goes: the game's hit test casts its ray from its own camera,
        so give it the gun direction in the game camera's frame (see vrshot.py)."""
        self.vrshot.set_shot(self.p, None if q_game is None else self.vrshot.shot_coords(q_game))


def run_immersive(vr, cal, verbose=False, ptt=None, aim_frame='render'):
    """Lean/duck as in Stage 1. The green ring is placed through the head-rotated render
    camera (where the target is seen); the shot itself goes through the game camera
    (vrshot.py), because the game's hit test ignores the render view. The fork does the
    head rotation and stereo itself. No screen calibration: the stance is taken from
    calib.json if there is one, else from the first head pose (recenter with the grip)."""
    import pine as P
    from head_writer import HeadWriter
    from aim_writer import AimWriter
    p = wait_for_game(P)
    head, aim, patches = HeadWriter(p), AimWriter(p), Patches(p)
    t0 = np.array(cal['t0']) if cal else None
    yaw0 = cal['yaw0'] if cal else None
    print(f'immersive bridge running (aim frame: {aim_frame}) -- Ctrl+C to stop. '
          f'Hold right GRIP 1.5 s to recenter.', flush=True)
    firing, grip_since, last_print = False, None, 0
    try:
        while True:
            patches.tick()
            poses = vr.poses()
            hmd = vr.hmd(poses)
            pose, st = vr.controller(poses, vr.right())
            if hmd is not None and t0 is None:
                t0, yaw0 = hmd[1].copy(), yaw_of(hmd[0])

            dx = dy = u = v = None
            q_game = None
            if hmd is not None:
                dx, dy = head_offsets(hmd, t0, yaw0)
                head.set(dx, dy)
                if pose is not None:
                    uv = project_aim(hmd, pose, yaw0, patches.render_tan, aim_frame)
                    if uv:
                        u, v = uv
                    q_game = aim_target(hmd, pose, yaw0)[1]
            patches.shot(q_game)

            if st:
                if not firing and st['trigger'] > TRIG_ON:
                    firing = True
                elif firing and st['trigger'] < TRIG_OFF:
                    firing = False
                if st['grip']:
                    grip_since = grip_since or time.time()
                    if time.time() - grip_since > RECENTER_S and hmd is not None:
                        t0, yaw0 = hmd[1].copy(), yaw_of(hmd[0])
                        patches.recenter()
                        beep(600); beep(900)
                        grip_since = float('inf')
                else:
                    grip_since = None
            if ptt:
                voice_tick(vr, ptt)
            aim.set(u, v, firing if st else None)

            if verbose and time.time() - last_print > 0.25:
                last_print = time.time()
                hs = f'lean={dx:+.2f} duck={dy:+.2f}' if dx is not None else 'hmd=?'
                a = f'aim=({u:.2f},{v:.2f})' if u is not None else 'aim=?'
                t = f"trig={st['trigger']:.2f}{' FIRE' if firing else ''}" if st else 'trig=?'
                print(f'{hs}  {a}  {t}  tan={patches.render_tan[0]:.2f}x{patches.render_tan[1]:.2f}',
                      flush=True)
            time.sleep(1 / HZ)
    except KeyboardInterrupt:
        pass
    finally:
        if ptt:
            ptt.release()
        aim.release()
        head.neutral()
        p.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--calibrate', action='store_true')
    ap.add_argument('--immersive', action='store_true',
                    help='Stage 2: pcsx2-vr fork in the headset (no screen calibration)')
    ap.add_argument('--aim-frame', choices=('render', 'logic'), default='render',
                    help='immersive: project the gun through the head-rotated or the game camera')
    ap.add_argument('--dry', action='store_true', help='no PINE writes, no clicks; print')
    ap.add_argument('-v', '--verbose', action='store_true')
    ap.add_argument('--voice-only', action='store_true', help='only left-hand push-to-talk')
    ap.add_argument('--no-voice', action='store_true', help='disable push-to-talk')
    ap.add_argument('--voice-title', default='',
                    help='text in the Claude Code terminal title, if several are open')
    args = ap.parse_args()
    ptt = None
    if not args.no_voice:
        from voice_ptt import PushToTalk
        ptt = PushToTalk(args.voice_title)
    try:
        vr = VR()
    except openvr.OpenVRError as e:
        raise SystemExit(f'SteamVR not reachable ({e}). Start SteamVR with the headset '
                         f'connected first.')
    try:
        if args.voice_only:
            return voice_only(vr, ptt)
        if args.immersive:
            cal = None
            if os.path.exists(CALIB):
                with open(CALIB) as f:
                    cal = json.load(f)
            return run_immersive(vr, cal, verbose=args.verbose, ptt=ptt, aim_frame=args.aim_frame)
        if args.calibrate or not os.path.exists(CALIB):
            cal = calibrate(vr)
            if args.calibrate:
                return
        else:
            with open(CALIB) as f:
                cal = json.load(f)
        run(vr, cal, dry=args.dry, verbose=args.verbose, ptt=ptt)
    finally:
        vr.shutdown()


if __name__ == '__main__':
    main()
