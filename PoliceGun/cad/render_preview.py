"""Headless: build the PoliceGun grip, render 4 workbench views to PNGs."""
import bpy, os, math
from mathutils import Vector

GRIP = "/Users/toddkaiser/Claude Code/Police 911/PoliceGun/cad/policegun_grip.py"
OUT = "/private/tmp/claude-501/-Users-toddkaiser-Claude-Code-Police-911/02863802-8714-41bd-84ec-e6e6cd1425d8/scratchpad"

# Build the model (runs build() at end of the grip script).
exec(compile(open(GRIP).read(), GRIP, "exec"))

obj = bpy.data.objects["PoliceGun_Body"]
bb = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
center = sum(bb, Vector()) / 8.0
size = max(max(v[i] for v in bb) - min(v[i] for v in bb) for i in range(3))
dist = size * 1.9

scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.render.resolution_x = 1000
scene.render.resolution_y = 1000
scene.render.film_transparent = False

sh = scene.display.shading
sh.light = "STUDIO"
sh.color_type = "SINGLE"
sh.single_color = (0.52, 0.57, 0.64)
sh.show_cavity = True
sh.cavity_type = "BOTH"
sh.show_object_outline = True
sh.background_type = "VIEWPORT"
sh.background_color = (0.10, 0.11, 0.13)
scene.display.render_aa = "16"

cam_data = bpy.data.cameras.new("cam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = size * 1.35
cam_data.clip_end = 10000
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

views = {
    "side":   Vector((1.0, 0.02, 0.06)),
    "iso":    Vector((0.9, -0.85, 0.5)),
    "muzzle": Vector((0.1, 1.0, 0.14)),
    "top":    Vector((0.02, 0.0, 1.0)),
}

for name, d in views.items():
    loc = center + d.normalized() * dist
    cam.location = loc
    direction = center - loc
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = os.path.join(OUT, f"pg_view_{name}.png")
    bpy.ops.render.render(write_still=True)
    print("rendered", name)

print("DIMS", tuple(round(x, 1) for x in obj.dimensions))
