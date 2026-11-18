"""Load a Meebit by token number: download, import, pose.

Works inside the add-on and from plain scripts (see tools/render.py).
"""
import math
import os
import sys
import tempfile
import urllib.request

import bpy
from mathutils import Matrix, Vector

CDN = "https://cdn.meebco.com/meebco-site/glb/{:05d}.glb"
FIRST, LAST = 1, 20000
USER_AGENT = "meebits-kit/0.1"

# The rig is the Unreal mannequin skeleton (87 bones). A Meebit stands in a T-pose, faces -Y,
# its left side (the "_l" bones) is +X, and one Blender unit is one metre.
POSES = {
    "ARMS_DOWN": "Arms down, the standard pose",
    "T_POSE": "T-pose, as the model ships",
}


class MeebitError(Exception):
    pass


def check_token(token):
    token = int(token)
    if not FIRST <= token <= LAST:
        raise MeebitError(f"Meebits run from {FIRST} to {LAST}, so there is no Meebit {token}")
    return token


def cache_dir():
    """Where downloaded models live. MEEBITS_KIT_CACHE wins; inside the add-on, Blender's own
    folder for the extension; otherwise the user's cache folder."""
    path = os.environ.get("MEEBITS_KIT_CACHE")
    if not path:
        try:
            path = bpy.utils.extension_path_user(__package__, path="models", create=True)
        except (ValueError, AttributeError, TypeError):
            if sys.platform == "darwin":
                base = os.path.expanduser("~/Library/Caches")
            elif sys.platform == "win32":
                base = os.environ.get("LOCALAPPDATA", tempfile.gettempdir())
            else:
                base = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
            path = os.path.join(base, "meebits-kit", "models")
    os.makedirs(path, exist_ok=True)
    return path


def fetch(token):
    """Path to the Meebit's GLB, downloaded once and kept in the cache."""
    token = check_token(token)
    path = os.path.join(cache_dir(), f"{token:05d}.glb")
    if os.path.exists(path):
        return path
    if not getattr(bpy.app, "online_access", True):
        raise MeebitError("Blender is offline. Turn on Allow Online Access in Preferences > System "
                          "(or run Blender with --online-mode) to download Meebits")
    req = urllib.request.Request(CDN.format(token), headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
    except OSError as e:
        raise MeebitError(f"Could not download Meebit {token}: {e}") from e
    if data[:4] != b"glTF":
        raise MeebitError(f"The download for Meebit {token} is not a GLB file")
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return path


def _rotate_world(rig, pb, axis, deg):
    """Turn a pose bone about its own head, around a world axis."""
    mw = rig.matrix_world
    head = (mw @ pb.matrix).to_translation()
    turn = Matrix.Translation(head) @ Matrix.Rotation(math.radians(deg), 4, axis) @ Matrix.Translation(-head)
    pb.matrix = mw.inverted() @ turn @ mw @ pb.matrix
    bpy.context.view_layer.update()


def pose(rig, name="ARMS_DOWN"):
    """Put the Meebit in a named pose. Clears any earlier pose first."""
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    if name == "T_POSE":
        return
    if name != "ARMS_DOWN":
        raise MeebitError(f"Unknown pose {name}")
    mw = rig.matrix_world
    for side in ("l", "r"):
        upper = rig.pose.bones[f"upperarm_{side}"]
        outward = 1 if (mw @ upper.matrix).to_translation().x > mw.to_translation().x else -1
        _rotate_world(rig, upper, "Y", 84 * outward)                       # the arm comes down to the side
        _rotate_world(rig, rig.pose.bones[f"lowerarm_{side}"], "X", -10)   # a soft bend at the elbow


def meshes_of(rig):
    return [o for o in rig.children_recursive if o.type == "MESH"]


def lowest_point(rig):
    """Lowest world height of the posed Meebit."""
    deps = bpy.context.evaluated_depsgraph_get()
    low = math.inf
    for o in meshes_of(rig):
        ev = o.evaluated_get(deps)
        me = ev.to_mesh()
        mw = ev.matrix_world
        for v in me.vertices:
            low = min(low, (mw @ v.co).z)
        ev.to_mesh_clear()
    return low


def height(rig):
    deps = bpy.context.evaluated_depsgraph_get()
    zs = []
    for o in meshes_of(rig):
        ev = o.evaluated_get(deps)
        zs += [(ev.matrix_world @ Vector(c)).z for c in ev.bound_box]
    return max(zs) - min(zs) if zs else 0.0


def load(token, pose_name="ARMS_DOWN", location=(0.0, 0.0, 0.0)):
    """Download (once), import and pose a Meebit. Returns its armature object.

    The Meebit gets its own collection, its feet on `location`, and faces -Y.
    """
    token = check_token(token)
    path = fetch(token)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    rig = next((o for o in new if o.type == "ARMATURE"), None)
    if rig is None:
        raise MeebitError(f"Meebit {token} came in without a rig")

    name = f"Meebit {token:05d}"
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    for o in new:
        # The importer adds a sphere that only draws the bones and files it under glTF_not_exported.
        if o.type == "MESH" and o.parent is None:
            continue
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
    rig.name = name
    rig.data.name = name
    rig["meebit_token"] = token
    rig.show_in_front = False
    rig.data.display_type = "STICK"

    rig.location = Vector(location)
    bpy.context.view_layer.update()
    pose(rig, pose_name)
    rig.location.z += location[2] - lowest_point(rig)   # feet on the floor
    bpy.context.view_layer.update()

    for o in bpy.context.selected_objects:
        o.select_set(False)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    return rig


def meebits_in_scene(scene=None):
    scene = scene or bpy.context.scene
    return [o for o in scene.objects if o.type == "ARMATURE" and "meebit_token" in o]
