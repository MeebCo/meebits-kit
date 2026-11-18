"""Render Meebits with the house look from the command line, no add-on install needed.

    blender -b --factory-startup --online-mode --python tools/render.py -- 8506 -o renders/08506.png
    blender -b --factory-startup --online-mode --python tools/render.py -- 1 2 3 -o renders/lineup.png

Several token numbers stand in a row, left to right as seen from the camera. Add --motion walk1 (and
--frame 20) to render a moment from one of Bailey's motions instead of the standing pose.
"""
import argparse
import os
import sys

import bpy

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "blender"))
from meebits_kit import core, look, motion  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser(prog="render.py")
ap.add_argument("tokens", type=int, nargs="+")
ap.add_argument("-o", "--output", required=True, help="PNG to write")
ap.add_argument("--pose", default="ARMS_DOWN", choices=sorted(core.POSES))
ap.add_argument("--motion", choices=motion.names(), help="play one of Bailey's motions instead of a pose")
ap.add_argument("--frame", type=int, help="frame of the motion to render (default: the middle)")
ap.add_argument("--samples", type=int, default=128)
ap.add_argument("--size", default="1080x1350", help="width x height in pixels")
ap.add_argument("--gap", type=float, default=0.75, help="metres between Meebits in a row")
ap.add_argument("--blend", help="also save the scene as this .blend")
args = ap.parse_args(argv)

bpy.ops.wm.read_factory_settings(use_empty=True)
n = len(args.tokens)
scene = bpy.context.scene
for i, token in enumerate(args.tokens):
    rig = core.load(token, args.pose, ((i - (n - 1) / 2) * args.gap, 0.0, 0.0))
    if args.motion:
        motion.apply(rig, args.motion)
if args.motion:
    scene.frame_set(args.frame or (scene.frame_start + scene.frame_end) // 2)
look.apply(scene, tuple(int(v) for v in args.size.lower().split("x")))
scene.cycles.samples = args.samples

# Factory settings render on the CPU. Use a GPU when this machine has one Cycles can use.
prefs = bpy.context.preferences.addons["cycles"].preferences
for kind in ("METAL", "OPTIX", "CUDA", "HIP", "ONEAPI"):
    try:
        prefs.compute_device_type = kind
    except TypeError:
        continue
    prefs.get_devices()
    gpus = [d for d in prefs.devices if d.type == kind]
    if gpus:
        for d in prefs.devices:
            d.use = d.type == kind
        scene.cycles.device = "GPU"
        break
else:
    prefs.compute_device_type = "NONE"
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = os.path.abspath(args.output)
os.makedirs(os.path.dirname(scene.render.filepath), exist_ok=True)
if args.blend:
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.blend))
bpy.ops.render.render(write_still=True)
print("Wrote", scene.render.filepath)
