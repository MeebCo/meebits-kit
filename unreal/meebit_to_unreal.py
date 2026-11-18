"""Turn a Meebit into a GLB that Unreal Engine can import. Runs inside Blender, in the background.

    blender -b --factory-startup --online-mode --python unreal/meebit_to_unreal.py -- 8506 Meebit_08506.glb [motions]

The MeebCo CDN serves the web copies: meshopt-compressed geometry and WebP textures, which Unreal's
glTF importer can't read. This writes the same Meebit with plain geometry and PNG textures. The rig
is unchanged (the Unreal mannequin's 87 bones in the T-pose), and the standard arms-down pose comes
along as a one-pose animation called ArmsDown. Bailey's motions come along too, one animation each, in the
version made for this Meebit's skeleton: all 23 by default, or a comma-separated list (idle1,walk1), or none.

meebits_kit_unreal.py runs this for you from inside the Unreal Editor.
"""
import os
import shutil
import sys
import tempfile

import bpy

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "blender"))
from meebits_kit import core, motion  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if len(argv) not in (2, 3):
    sys.exit("usage: blender -b --online-mode --python meebit_to_unreal.py -- <token> <out.glb> [all|none|idle1,walk1]")
token, out = core.check_token(argv[0]), os.path.abspath(argv[1])
wanted = argv[2] if len(argv) == 3 else "all"
motions = motion.names() if wanted == "all" else [] if wanted == "none" else [m for m in wanted.split(",") if m]

bpy.ops.wm.read_factory_settings(use_empty=True)
rig = core.load(token, "T_POSE")
rig.location = (0.0, 0.0, 0.0)
for o in list(bpy.data.objects):          # the importer's bone-drawing sphere
    if o.type == "MESH" and o.parent is None:
        bpy.data.objects.remove(o)
parts = core.meshes_of(rig)               # one mesh with a material slot per part, not eight meshes
with bpy.context.temp_override(active_object=parts[0], object=parts[0], selected_objects=parts,
                               selected_editable_objects=parts):
    bpy.ops.object.join()
parts[0].name = parts[0].data.name = f"Meebit_{token:05d}"
bpy.context.view_layer.update()

for name in motions:                      # in place: in Unreal, move the Meebit (or use root motion) yourself
    action = motion.apply(rig, name, move=False)
    action.name = name
    action.use_fake_user = True

rig.animation_data_create()
arms_down = bpy.data.actions.new("ArmsDown")
arms_down.use_fake_user = True
rig.animation_data.action = arms_down
core.pose(rig, "ARMS_DOWN")
for frame in (1, 2):                      # two equal keys: an animation that holds one pose
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
        for path in ("location", "rotation_quaternion", "scale"):
            pb.keyframe_insert(path, frame=frame)
bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, 2


def texture_names():
    """Image_7 becomes head_BaseColor, head_Normal or head_ORM, after the material and the job."""
    names = {}
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        for n in mat.node_tree.nodes:
            if n.type != "TEX_IMAGE" or not n.image or n.image in names:
                continue
            feeds = {l.to_node.type for out in n.outputs for l in out.links}
            if "NORMAL_MAP" in feeds:
                job = "Normal"
            elif n.image.colorspace_settings.name == "sRGB":
                job = "BaseColor"
            else:
                job = "ORM"
            names[n.image] = f"{mat.name}_{job}"
    return names


names = texture_names()
pngs = tempfile.mkdtemp(prefix="meebit_png_")
for img in list(bpy.data.images):         # WebP in, PNG out: write each texture as a PNG and use that
    if img.type != "IMAGE":
        continue
    name = names.get(img, img.name)
    path = os.path.join(pngs, f"{bpy.path.clean_name(name)}.png")
    img.file_format = "PNG"
    img.save(filepath=path)
    png = bpy.data.images.load(path)
    png.colorspace_settings.name = img.colorspace_settings.name
    png.alpha_mode = img.alpha_mode
    img.user_remap(png)
    png.name = name

os.makedirs(os.path.dirname(out), exist_ok=True)
bpy.ops.export_scene.gltf(
    filepath=out,
    export_format="GLB",
    export_image_format="AUTO",
    export_draco_mesh_compression_enable=False,
    export_animations=True,
    export_animation_mode="ACTIONS",
    export_def_bones=False,
    export_rest_position_armature=True,
    export_yup=True,
)
shutil.rmtree(pngs, ignore_errors=True)
print("Wrote", out)
