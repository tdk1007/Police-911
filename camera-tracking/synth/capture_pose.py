"""Capture the player's real standing movement envelope from the Link 2C.

Runs mediapipe pose on the REAL camera (not our synthetic feed) and records four
held poses. The result (capture_pose.json) is the raw material for the transfer
function: it tells us how far your nose/shoulders/hips actually travel between
neutral, a full lean each way, and a deep squat, so we can map that onto the
game's narrow seated dodge band.

    py capture_pose.py            # auto-picks the Link 2C
    py capture_pose.py --list     # list cameras and exit
    py capture_pose.py --device N # use DirectShow device index N

A window shows you live with your pose skeleton. For each prompt, get into the
pose, hold still, and press SPACE to record it (Q quits, R re-does the last one).
"""
import json, os, sys, time
import cv2
import numpy as np

try:
    import mediapipe as mp
except Exception as e:
    print("mediapipe import failed:", e)
    sys.exit(1)

from pygrabber.dshow_graph import FilterGraph

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'capture_pose.json')

POSES = [
    ("neutral",    "Stand comfortably facing the TV, arms relaxed."),
    ("lean_left",  "Lean your whole upper body as far LEFT as you would to dodge."),
    ("lean_right", "Lean as far RIGHT as you would to dodge."),
    ("squat",      "Squat / duck down as low as you would to take cover."),
]

# mediapipe landmark indices we care about
NOSE, L_SH, R_SH, L_HIP, R_HIP = 0, 11, 12, 23, 24


def pick_device():
    names = FilterGraph().get_input_devices()
    for i, n in enumerate(names):
        print(f"  [{i}] {n}")
    for i, n in enumerate(names):
        if "Link 2C" in n or "Insta360" in n:
            return i, n
    return 0, names[0] if names else "?"


def landmarks(res, w, h):
    if not res.pose_landmarks:
        return None
    lm = res.pose_landmarks.landmark
    def pt(i):
        return np.array([lm[i].x * w, lm[i].y * h, lm[i].visibility])
    return {
        "nose": pt(NOSE).tolist(),
        "l_sh": pt(L_SH).tolist(), "r_sh": pt(R_SH).tolist(),
        "l_hip": pt(L_HIP).tolist(), "r_hip": pt(R_HIP).tolist(),
    }


def main():
    if "--list" in sys.argv:
        pick_device(); return
    if "--device" in sys.argv:
        dev = int(sys.argv[sys.argv.index("--device") + 1])
        name = "(manual)"
    else:
        dev, name = pick_device()
    print(f"\nusing camera [{dev}] {name}\n")

    cap = cv2.VideoCapture(dev, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    pose = mp.solutions.pose.Pose(model_complexity=1,
                                  min_detection_confidence=0.5,
                                  min_tracking_confidence=0.5)
    draw = mp.solutions.drawing_utils

    recorded = {}
    idx = 0
    print("SPACE = record this pose   R = redo last   Q = quit\n")
    while idx < len(POSES):
        key, prompt = POSES[idx]
        ok, frame = cap.read()
        if not ok:
            print("camera read failed"); break
        frame = cv2.flip(frame, 1)                 # mirror = feels natural
        h, w = frame.shape[:2]
        res = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        if res.pose_landmarks:
            draw.draw_landmarks(frame, res.pose_landmarks,
                                mp.solutions.pose.POSE_CONNECTIONS)
        got = landmarks(res, w, h)
        colour = (0, 255, 0) if got else (0, 0, 255)
        cv2.putText(frame, f"POSE {idx+1}/{len(POSES)}: {key}", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, colour, 2)
        cv2.putText(frame, prompt, (20, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        cv2.putText(frame, "SPACE record  R redo  Q quit", (20, h - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 0), 1)
        cv2.imshow("Police 24/7 - pose capture", frame)

        k = cv2.waitKey(1) & 0xFF
        if k == ord('q'):
            break
        if k == ord('r') and idx > 0:
            idx -= 1
            recorded.pop(POSES[idx][0], None)
            continue
        if k == ord(' '):
            if not got:
                print(f"  {key}: no pose detected, try again")
                continue
            recorded[key] = got
            print(f"  recorded {key}")
            idx += 1

    cap.release()
    cv2.destroyAllWindows()

    if len(recorded) == len(POSES):
        # summarise the envelope in shoulder-normalised units
        n = recorded["neutral"]
        sh_w = abs(n["l_sh"][0] - n["r_sh"][0]) or 1.0   # shoulder width = our scale
        nose0 = n["nose"]
        summary = {}
        for key, p in recorded.items():
            dx = (p["nose"][0] - nose0[0]) / sh_w
            dy = (p["nose"][1] - nose0[1]) / sh_w
            summary[key] = {"nose_dx_shoulders": round(dx, 3),
                            "nose_dy_shoulders": round(dy, 3)}
        json.dump({"raw": recorded, "shoulder_px": sh_w, "summary": summary},
                  open(OUT, "w"), indent=1)
        print(f"\nsaved {OUT}")
        print("envelope (nose travel, in shoulder-widths from neutral):")
        for key, s in summary.items():
            print(f"  {key:11s} dx={s['nose_dx_shoulders']:+.2f}  dy={s['nose_dy_shoulders']:+.2f}")
    else:
        print("\nincomplete capture, nothing saved")


if __name__ == '__main__':
    main()
