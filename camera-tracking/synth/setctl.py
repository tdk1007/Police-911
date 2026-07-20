"""setctl.py k=v [k=v ...]  -- update control.json (no BOM, unlike PowerShell).

    py setctl.py mode=player anim=sweep_x amp=0.75 period=6
    py setctl.py anim=none dx=-0.5 dy=0
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONTROL = os.path.join(HERE, 'control.json')

cur = {}
if os.path.exists(CONTROL):
    try:
        with open(CONTROL, encoding='utf-8-sig') as f:
            cur = json.load(f)
    except Exception:
        cur = {}


def coerce(v):
    if v in ('true', 'false'):
        return v == 'true'
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


for arg in sys.argv[1:]:
    k, _, v = arg.partition('=')
    cur[k] = coerce(v)

with open(CONTROL, 'w', encoding='utf-8') as f:
    json.dump(cur, f)
print(json.dumps(cur))
