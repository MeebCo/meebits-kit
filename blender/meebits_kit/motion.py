"""Bailey's motion library: play any of the 23 motions on any Meebit.

Each motion comes in three versions, one per Meebit skeleton: male (also Pig, Elephant, Robot, Skeleton
and Dissected Meebits), female and visitor. The right one is picked from the Meebit's arm length.
See motions/README.md for the file format.
"""
import json
import os

import bpy
from mathutils import Matrix, Quaternion, Vector

from . import core

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "motions")
ORDER = ("idle", "walk", "run", "chat", "greet", "present")
ARM_LENGTH = {"female": 0.336, "male": 0.37, "visitor": 0.652}   # shoulder to wrist, metres
_cache = {}


def names():
    """Motion names in library order: idle1..idle5, walk1.., run.., chat.., greet.., present.."""
    found = [f[:-5] for f in os.listdir(DIR) if f.endswith(".json")]

    def key(n):
        kind = n.rstrip("0123456789")
        return (ORDER.index(kind) if kind in ORDER else len(ORDER), kind, int(n[len(kind):] or 0))
    return sorted(found, key=key)


def load(name):
    if name not in _cache:
        path = os.path.join(DIR, f"{name}.json")
        if not os.path.exists(path):
            raise core.MeebitError(f"There is no motion called {name}")
        with open(path) as f:
            _cache[name] = json.load(f)
    return _cache[name]


def body_type(rig):
    """male, female or visitor, from the rest pose's arm length."""
    b = rig.data.bones
    arm = (b["hand_l"].head_local - b["upperarm_l"].head_local).length
    return min(ARM_LENGTH, key=lambda t: abs(ARM_LENGTH[t] - arm))


def _new_fcurve(action, rig, path, index, group):
    if hasattr(action, "fcurve_ensure_for_datablock"):          # Blender 4.4+
        fc = action.fcurve_ensure_for_datablock(rig, path, index=index)
        strip = action.layers[0].strips[0]
        bag = strip.channelbag(rig.animation_data.action_slot)
        fc.group = bag.groups.get(group) or bag.groups.new(group)
        return fc
    return action.fcurves.new(path, index=index, action_group=group)


def _write(action, rig, path, index, group, frames, values, cyclic):
    fc = _new_fcurve(action, rig, path, index, group)
    fc.keyframe_points.add(len(frames))
    fc.keyframe_points.foreach_set("co", [v for pair in zip(frames, values) for v in pair])
    fc.keyframe_points.foreach_set("interpolation", [bpy.types.Keyframe.bl_rna.properties["interpolation"]
                                                     .enum_items["LINEAR"].value] * len(frames))
    if cyclic:
        fc.modifiers.new("CYCLES")
    fc.update()
    return fc


def stop(rig):
    """Take the motion off and go back to the T-pose."""
    if rig.animation_data:
        rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def apply(rig, name, move=True, body=None, start=1, *, set_scene_timing=True):
    """Put motion `name` on the Meebit as an action of the same name, starting at frame `start`.

    move: for walks and runs, also move the Meebit forward at the pace of its feet (it faces -Y).
    body: force a skeleton (male, female, visitor) instead of measuring the Meebit.
    set_scene_timing: set the scene FPS, range and playhead for preview. With False, keep
    the scene timing and space the motion keys to retain the clip's original speed.
    Returns the action.
    """
    clip = load(name)
    body = body or body_type(rig)
    data = clip["types"][body]
    rows = data["frames"]
    n = len(rows)
    scene = bpy.context.scene
    fps = clip.get("fps", 30)
    frame_step = 1 if set_scene_timing else scene.render.fps / (scene.render.fps_base * fps)
    frames = [start + i * frame_step for i in range(n)]
    loop = clip.get("loop", True)

    for pb in rig.pose.bones:                    # start from the T-pose
        pb.matrix_basis = Matrix.Identity(4)
    rig.animation_data_create()
    action = bpy.data.actions.new(f"{rig.name} {name}")
    action["meebit_motion"] = name
    rig.animation_data.action = action

    # The motion's turns are relative to the T-pose in world orientation (Z up, facing -Y). Bring them
    # into this rig's space, then work out each bone's own rotation from its parent's.
    world = rig.matrix_world.to_3x3().normalized()
    to_rig, from_rig = world.inverted(), world
    scale = rig.matrix_world.to_scale()[0] or 1.0
    bones = [b for b in rig.data.bones if b.name in rows[0]]
    rest = {b.name: b.matrix_local.to_3x3().normalized() for b in rig.data.bones}
    quats = {b.name: [] for b in bones}
    pelvis = []
    for row in rows:
        posed = {}

        def pose_rot(b):
            if b.name in posed:
                return posed[b.name]
            if b.name in row:
                r = to_rig @ Quaternion(row[b.name]).to_matrix() @ from_rig @ rest[b.name]
            elif b.parent:
                r = pose_rot(b.parent) @ rest[b.parent.name].inverted() @ rest[b.name]
            else:
                r = rest[b.name]
            posed[b.name] = r
            return r

        for b in bones:
            if b.parent:
                basis = rest[b.name].inverted() @ rest[b.parent.name] @ pose_rot(b.parent).inverted() @ pose_rot(b)
            else:
                basis = rest[b.name].inverted() @ pose_rot(b)
            q = basis.to_quaternion()
            prev = quats[b.name][-1] if quats[b.name] else None
            if prev is not None and prev.dot(q) < 0:   # keep neighbouring keys on the same side
                q.negate()
            quats[b.name].append(q)
        off = to_rig @ Vector(row.get("pelvis_offset", (0, 0, 0))) / scale
        pelvis.append(rest["pelvis"].inverted() @ off)

    for b in bones:
        pb = rig.pose.bones[b.name]
        pb.rotation_mode = "QUATERNION"
        path = f'pose.bones["{b.name}"]'
        for i in range(4):
            _write(action, rig, f"{path}.rotation_quaternion", i, b.name, frames,
                   [q[i] for q in quats[b.name]], loop)
    for i in range(3):
        _write(action, rig, 'pose.bones["pelvis"].location', i, "pelvis", frames, [p[i] for p in pelvis], loop)

    speed = data.get("speed", 0.0)
    if move and speed and clip.get("travel"):
        # Walks and runs are baked in place: carry the Meebit forward, one cycle's distance per cycle.
        forward = (rig.matrix_world.to_3x3() @ Vector((0, -1, 0)))
        forward.z = 0
        forward = forward.normalized() * speed * (n - 1) / fps
        here = rig.location.copy()
        for i in range(2):
            fc = _new_fcurve(action, rig, "location", i, "Object Transforms")
            fc.keyframe_points.add(2)
            fc.keyframe_points.foreach_set("co", [frames[0], here[i], frames[-1], here[i] + forward[i]])
            fc.keyframe_points.foreach_set("interpolation", [bpy.types.Keyframe.bl_rna.properties[
                "interpolation"].enum_items["LINEAR"].value] * 2)
            mod = fc.modifiers.new("CYCLES")
            mod.mode_before = mod.mode_after = "REPEAT_OFFSET"
            fc.update()

    if set_scene_timing:
        scene.render.fps, scene.render.fps_base = fps, 1.0
        scene.frame_start, scene.frame_end = start, max(start + n - 1, start + 1)
        scene.frame_set(start)
    return action
