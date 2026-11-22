"""Make an iPhone spatial Lock Screen wallpaper of any Meebit, no add-on install needed.

    blender -b --factory-startup --online-mode --python tools/wallpaper.py -- 8506
    blender -b --factory-startup --online-mode --python tools/wallpaper.py -- 8506 --scene giftbox
    blender -b --factory-startup --online-mode --python tools/wallpaper.py -- 8506 --preview

Writes <token>_<scene>_iphone.png (put this one on your phone), a 16-bit master, a mask of the Meebit
and a report with the framing checks, in renders/ unless you pass -o. --preview renders at phone size
with fewer samples, to check the look in a few seconds before the full render. --blend saves the scene,
so you can open it in Blender and change things yourself.
"""
import argparse
import os
import sys

import bpy

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "blender"))
from meebits_kit import wallpaper  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser(prog="wallpaper.py")
ap.add_argument("tokens", type=int, nargs="+", help="one wallpaper per token")
ap.add_argument("--scene", default="capsule", choices=sorted(wallpaper.SCENES))
ap.add_argument("-o", "--output", default="renders", help="folder to write into")
ap.add_argument("--samples", type=int, default=64)
ap.add_argument("--scale", type=float, default=2.0, help="2 makes 2640 x 5736, the size that stays sharp on the phone")
ap.add_argument("--preview", action="store_true", help="1320 x 2868 at 16 samples: a quick look")
ap.add_argument("--blend", action="store_true", help="also save each scene as a .blend next to the images")
args = ap.parse_args(argv)
if args.preview:
    args.scale, args.samples = 1.0, 16

failed = []
for token in args.tokens:
    report = wallpaper.make(token, args.scene, args.output, args.samples, args.scale)
    stem = os.path.join(os.path.abspath(args.output), f"{token:05d}_{args.scene}")
    if args.blend:
        bpy.ops.wm.save_as_mainfile(filepath=stem + ".blend")
    print(f"\nMeebit {token} in the {args.scene}: {stem}_iphone.png")
    for k in ("clock_overlap_pct", "feet_to_buttons_px", "zoom_margin_px", "edge_weak_pct"):
        print(f"  {k}: {report.get(k)}")
    for f in report["fails"]:
        print("  CHECK FAILED:", f)
    if report["fails"]:
        failed.append(token)
if failed:
    print("\nSome checks failed; see the reports. The images are still written.")
