"""Write the motion library from Bailey's motion pack (a .blend, not in this repo) to motions/*.json.

    blender -b --factory-startup --disable-autoexec --python tools/export_motions.py -- <motion pack>.blend

Maintainers run this; everyone else uses the JSON files it writes. The pack holds each motion baked for the
three Meebit skeletons (<name>__male, <name>__female, <name>__visitor) on its STAGE_<type> rigs.

Each frame stores, for every animated bone, its rotation relative to the T-pose in the rig's own space
(not the bone's), and the pelvis's offset from its T-pose place. A rig whose bones point another way in
the rest pose still plays the motion correctly. See motions/README.md for the format.
"""
import json
import os
import sys

import bpy
from mathutils import Matrix, Quaternion

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "blender", "meebits_kit", "motions")
TYPES = ("male", "female", "visitor")
RENAME = {"head_old": "head"}            # the pack's rigs call the head bone head_old
DIGITS = 5

pack = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
with bpy.data.libraries.load(pack, link=False) as (src, dst):
    dst.objects = [f"STAGE_{t}" for t in TYPES]
    dst.actions = [a for a in src.actions if "__" in a and a.split("__")[1] in TYPES]
rigs = {t: o for t, o in zip(TYPES, dst.objects)}
actions = {a.name: a for a in dst.actions}
# Walks and runs are baked in place. These are their speeds over the ground in metres a second, from the
# motion library, so a Meebit can be moved along at the pace its feet are going.
SPEED = {"run1": (3.52, 3.408, 3.52), "run2": (2.713, 2.439, 2.713), "run3": (1.922, 1.702, 1.922),
         "walk1": (0.807, 0.767, 0.799), "walk2": (0.411, 0.377, 0.409), "walk3": (0.887, 0.806, 0.887),
         "walk4": (1.303, 1.248, 1.289), "walk5": (0.242, 0.294, 0.228)}           # male, female, visitor

# How each kind of motion plays: greet and present play once, walk and run move the Meebit forward.
KINDS = {"idle": (True, False), "walk": (True, True), "run": (True, True), "chat": (True, False),
         "greet": (False, False), "present": (False, False)}


def channels(action):
    try:
        fcs = list(action.fcurves)
    except AttributeError:           # Blender 4.4+: layered actions
        fcs = [f for l in action.layers for s in l.strips for cb in s.channelbags for f in cb.fcurves]
    out = {}
    for f in fcs:
        if not f.data_path.startswith("pose.bones"):
            continue
        bone = f.data_path.split('"')[1]
        out.setdefault(bone, {})[(f.data_path.rsplit(".", 1)[1], f.array_index)] = f
    return out


def bake(rig, action):
    """Rig-space rotation of each animated bone relative to its rest, per frame, and the pelvis offset."""
    ch = channels(action)
    bones = [b for b in rig.data.bones if b.name in ch]          # parents come before children
    first, last = (int(round(x)) for x in action.frame_range)
    rest = {b.name: b.matrix_local for b in rig.data.bones}
    # Read from the object's own settings: a rig loaded from a file but not placed in a scene has no
    # world matrix yet. The pack's rigs are in centimetres (scale 0.01).
    world = rig.rotation_euler.to_matrix()
    unit = rig.scale[0]
    frames = []
    for fr in range(first, last + 1):
        pose = {}
        rows = {}

        def matrix(b):
            """Pose matrix of a bone in rig space; bones without keys follow their parent."""
            if b.name in pose:
                return pose[b.name]
            c = ch.get(b.name, {})
            q = [c[("rotation_quaternion", i)].evaluate(fr) if ("rotation_quaternion", i) in c else (1, 0, 0, 0)[i]
                 for i in range(4)]
            t = [c[("location", i)].evaluate(fr) if ("location", i) in c else 0.0 for i in range(3)]
            basis = Matrix.Translation(t) @ Quaternion(q).normalized().to_matrix().to_4x4()
            if b.parent:
                m = matrix(b.parent) @ (rest[b.parent.name].inverted() @ rest[b.name]) @ basis
            else:
                m = rest[b.name] @ basis
            pose[b.name] = m
            return m

        for b in bones:
            m = matrix(b)
            delta = world @ (m.to_3x3() @ rest[b.name].to_3x3().inverted()) @ world.inverted()
            q = delta.to_quaternion()
            rows[RENAME.get(b.name, b.name)] = [round(v, 4) for v in (q.w, q.x, q.y, q.z)]
        pelvis = matrix(rig.data.bones["pelvis"]).to_translation() - rest["pelvis"].to_translation()
        rows["pelvis_offset"] = [round(v * unit, DIGITS) for v in world @ pelvis]
        frames.append(rows)
    return frames


os.makedirs(OUT, exist_ok=True)
names = sorted({a.split("__")[0] for a in actions})
for name in names:
    kind = name.rstrip("0123456789")
    loop, travel = KINDS.get(kind, (True, False))
    clip = {"name": name, "fps": 30, "category": kind, "loop": loop, "travel": travel, "by": "Bailey, MeebCo",
            "types": {}}
    for t in TYPES:
        a = actions.get(f"{name}__{t}")
        if a is None:
            print(f"missing {name}__{t}")
            continue
        clip["types"][t] = {"speed": SPEED[name][TYPES.index(t)] if name in SPEED else 0.0,
                            "frames": bake(rigs[t], a)}
    with open(os.path.join(OUT, f"{name}.json"), "w") as f:
        json.dump(clip, f, separators=(",", ":"))
    print("wrote", name, {t: len(v["frames"]) for t, v in clip["types"].items()})
