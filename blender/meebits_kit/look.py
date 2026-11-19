"""The house look: AgX, a sky, one warm sun, a plain floor and a camera at the Meebits' eye level.

The camera never looks up at them: a Meebit feels magnificent through the light and the setting, not
because the audience has to crane its neck.

Running it again updates the same lights, floor and camera instead of adding new ones.
"""
import math

import bpy
from mathutils import Euler, Vector

from . import core

LOOK = "Meebits Look"
SUN_ELEVATION = 38     # degrees above the horizon
SUN_FROM = -35         # compass direction the sun comes from; 0 is from behind the camera
CAMERA_TURN = 18       # degrees the camera swings round to the Meebit's right of straight on
HEAD_TO_EYES = 0.17    # metres from the head bone up to a Meebit's eyes
LENS = 50
FLOOR = "#cfc8bd"


def _srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _hex(h):
    h = h.lstrip("#")
    return tuple(_srgb_to_linear(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4)) + (1.0,)


def _collection(scene):
    coll = bpy.data.collections.get(LOOK)
    if coll is None:
        coll = bpy.data.collections.new(LOOK)
    if coll.name not in scene.collection.children:
        scene.collection.children.link(coll)
    return coll


def _object(coll, name, data):
    ob = bpy.data.objects.get(name)
    if ob is None:
        ob = bpy.data.objects.new(name, data)
    if ob.name not in coll.objects:
        coll.objects.link(ob)
    return ob


def _render_settings(scene, resolution):
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 128
    scene.cycles.use_denoising = True
    try:
        if bpy.context.preferences.addons["cycles"].preferences.compute_device_type != "NONE":
            scene.cycles.device = "GPU"
    except (KeyError, AttributeError):
        pass
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    for look in ("AgX - Medium High Contrast", "Medium High Contrast"):
        try:
            scene.view_settings.look = look
            break
        except TypeError:
            continue
    scene.view_settings.exposure = 0.0


def _sky(scene):
    world = bpy.data.worlds.get(LOOK) or bpy.data.worlds.new(LOOK)
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    for kind in ("MULTIPLE_SCATTERING", "NISHITA"):
        try:
            sky.sky_type = kind
            break
        except TypeError:
            continue
    if hasattr(sky, "sun_disc"):
        sky.sun_disc = False
    if hasattr(sky, "sun_elevation"):
        sky.sun_elevation = math.radians(SUN_ELEVATION)
        sky.sun_rotation = math.radians(SUN_FROM + 90)
    bg.inputs["Strength"].default_value = 0.3
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    scene.world = world


def _sun(coll):
    data = bpy.data.lights.get(f"{LOOK} Sun") or bpy.data.lights.new(f"{LOOK} Sun", "SUN")
    data.energy = 4.0
    data.color = (1.0, 0.93, 0.84)
    data.angle = math.radians(3)
    sun = _object(coll, f"{LOOK} Sun", data)
    el, az = math.radians(SUN_ELEVATION), math.radians(SUN_FROM)
    towards_sun = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    sun.rotation_euler = (-towards_sun).to_track_quat("-Z", "Y").to_euler()
    return sun


def _floor(coll):
    mesh = bpy.data.meshes.get(f"{LOOK} Floor")
    if mesh is None:
        mesh = bpy.data.meshes.new(f"{LOOK} Floor")
        s = 50.0
        mesh.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    mat = bpy.data.materials.get(f"{LOOK} Floor") or bpy.data.materials.new(f"{LOOK} Floor")
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = _hex(FLOOR)
    bsdf.inputs["Roughness"].default_value = 0.85
    if not mesh.materials:
        mesh.materials.append(mat)
    return _object(coll, f"{LOOK} Floor", mesh)


def _camera(scene, coll, rigs):
    data = bpy.data.cameras.get(f"{LOOK} Camera") or bpy.data.cameras.new(f"{LOOK} Camera")
    data.lens = LENS
    data.sensor_fit = "AUTO"
    data.clip_start, data.clip_end = 0.05, 500
    cam = _object(coll, f"{LOOK} Camera", data)
    scene.camera = cam

    deps = bpy.context.evaluated_depsgraph_get()
    pts = []
    for rig in rigs:
        for o in core.meshes_of(rig):
            ev = o.evaluated_get(deps)
            pts += [ev.matrix_world @ Vector(c) for c in ev.bound_box]
    if not pts:
        pts = [Vector((-0.4, -0.3, 0)), Vector((0.4, 0.3, 1.4))]
    # The Meebits face -Y, so the camera looks along +Y: swing it round, keep it level, let Blender find
    # where it has to stand for everything to fit, and step back for some air. Then raise or lower it to
    # the Meebits' eye level and slide the frame (lens shift) so the framing stays the same and upright
    # lines stay upright.
    coords = [c for p in pts for c in p]
    centre = sum(pts, Vector()) / len(pts)
    data.shift_x = data.shift_y = 0.0
    cam.rotation_euler = Euler((math.radians(90), 0, math.radians(-CAMERA_TURN)), "XYZ")
    bpy.context.view_layer.update()
    loc, _ = cam.camera_fit_coords(deps, coords)
    cam.location = centre + (Vector(loc) - centre) * 1.18
    eyes = [(rig.matrix_world @ rig.pose.bones["head"].head).z + HEAD_TO_EYES * rig.matrix_world.to_scale()[2]
            for rig in rigs if "head" in rig.pose.bones]
    if eyes:
        view = cam.matrix_world.to_3x3() @ Vector((0, 0, -1))
        distance = (centre - cam.location).dot(view)
        frame = distance * data.sensor_width / data.lens        # the frame's longer side, at the Meebits
        eye = sum(eyes) / len(eyes)
        data.shift_y = (cam.location.z - eye) / frame
        cam.location.z = eye
    return cam


def apply(scene=None, resolution=(1080, 1350)):
    """Light the scene and frame every Meebit in it at this size (a 4:5 portrait by default).
    Returns the camera."""
    scene = scene or bpy.context.scene
    coll = _collection(scene)
    _render_settings(scene, resolution)
    _sky(scene)
    _sun(coll)
    _floor(coll)
    return _camera(scene, coll, core.meebits_in_scene(scene))
