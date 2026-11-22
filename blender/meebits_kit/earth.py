"""The Earth from orbit, from NASA's maps, and a field of round stars.

The maps are NASA's (Visible Earth / Earth Observatory). The kit downloads them from NASA the first time
a scene needs them, about 75 MB, and keeps a smaller working copy of each next to the Meebit cache. No map
lives in this repo.
"""
import math
import os
import urllib.request

import bpy
import numpy as np
from mathutils import Vector

from . import core

NASA = "https://assets.science.nasa.gov/content/dam/science/esd/eo/images"
SOURCES = {
    "colour": NASA + "/bmng/bmng-topography-bathymetry/december/world.topo.bathy.200412.3x21600x10800.jpg",
    "relief": NASA + "/bmng/topography/gebco_08_rev_elev_21600x10800.jpg",
    "ocean": NASA + "/bmng/bathymetry/gebco_08_rev_bath_21600x10800.jpg",
    "night": NASA + "/imagerecords/144000/144898/BlackMarble_2016_3km.jpg",
}
# the working copies the scene loads: (file, width) at a 2:1 aspect
WORKING = {
    "colour": ("earth_color_16k.jpg", 16384),
    "relief": ("earth_relief_8k.png", 8192),
    "ocean": ("earth_ocean_mask_8k.png", 8192),
    "night": ("earth_night_8k.jpg", 8192),
}


def maps_dir():
    path = os.path.join(os.path.dirname(core.cache_dir()), "earth")
    os.makedirs(path, exist_ok=True)
    return path


def _download(url, path):
    if not getattr(bpy.app, "online_access", True):
        raise core.MeebitError("Blender is offline. Turn on Allow Online Access in Preferences > System "
                               "(or run Blender with --online-mode) to download the Earth maps")
    print("Downloading", url, flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": core.USER_AGENT})
    tmp = path + ".part"
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        while True:
            block = r.read(1 << 20)
            if not block:
                break
            f.write(block)
    os.replace(tmp, path)


def _derive(kind, src, dst, width):
    """Scale a 21600 px NASA map down to its working size. The full maps cost about 1 GB of memory each
    in Blender, so the scene never loads them."""
    img = bpy.data.images.load(src)
    img.scale(width, width // 2)
    if kind == "ocean":
        # the bathymetry map has white land (250 and up); the mask is white where there's ocean
        px = np.empty(width * (width // 2) * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        grey = px[0::4]
        ocean = (grey < 250 / 255).astype(np.float32)
        px[0::4] = px[1::4] = px[2::4] = ocean
        px[3::4] = 1.0
        img.pixels.foreach_set(px)
    img.filepath_raw = dst
    img.file_format = "JPEG" if dst.endswith(".jpg") else "PNG"
    img.save(filepath=dst, quality=92) if dst.endswith(".jpg") else img.save(filepath=dst)
    bpy.data.images.remove(img)


def maps():
    """Paths of the four working maps, downloading and scaling them once."""
    out = {}
    folder = maps_dir()
    for kind, (name, width) in WORKING.items():
        dst = os.path.join(folder, name)
        if not os.path.exists(dst):
            src = os.path.join(folder, os.path.basename(SOURCES[kind]))
            if not os.path.exists(src):
                _download(SOURCES[kind], src)
            _derive(kind, src, dst, width)
            os.remove(src)                       # the 21600 px original isn't needed again
        out[kind] = dst
    return out


def _img(nt, path, colorspace="sRGB", interp="Cubic"):
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = bpy.data.images.get(os.path.basename(path)) or bpy.data.images.load(path)
    n.image.colorspace_settings.name = colorspace
    n.interpolation = interp
    return n


def earth(name, centre, radius, spin_deg=0.0, tilt_deg=-45.0, sun_from=(0.85, -0.55, 0.45),
          link_lights=None, hex_lin=None):
    """The Earth in four layers, each at its own depth, which is what iOS's spatial effect feeds on:
      1. the surface: NASA Blue Marble colour, relief as bump, glossy oceans with a sun glint, matte land
      2. city lights (NASA Black Marble) on the night side past the terminator
      3. a cloud shell just above the surface, shadowing it
      4. a thin blue glow of atmosphere on the limb, a crisp edge against space
    Lit by its own sun, linked to the Earth alone, so the room's lights stay the room's."""
    paths = maps()
    sun_v = Vector(sun_from).normalized()
    parts = []
    bpy.ops.mesh.primitive_uv_sphere_add(segments=384, ring_count=192, radius=radius, location=centre)
    e = bpy.context.active_object
    e.name = name
    e.rotation_euler = (math.radians(tilt_deg), 0, math.radians(spin_deg))
    for pg in e.data.polygons:
        pg.use_smooth = True
    m = bpy.data.materials.new(name + "_surface")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    col = _img(nt, paths["colour"])
    rel = _img(nt, paths["relief"], "Non-Color")
    ocn = _img(nt, paths["ocean"], "Non-Color", "Linear")
    ngt = _img(nt, paths["night"])
    nt.links.new(col.outputs["Color"], b.inputs["Base Color"])
    rough = nt.nodes.new("ShaderNodeMapRange")                       # oceans glossy, land matte
    rough.inputs["To Min"].default_value, rough.inputs["To Max"].default_value = 0.85, 0.22
    nt.links.new(ocn.outputs["Color"], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], b.inputs["Roughness"])
    spec = nt.nodes.new("ShaderNodeMapRange")
    spec.inputs["To Min"].default_value, spec.inputs["To Max"].default_value = 0.25, 0.75
    nt.links.new(ocn.outputs["Color"], spec.inputs["Value"])
    nt.links.new(spec.outputs["Result"], b.inputs["Specular IOR Level"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = radius * 0.0015
    nt.links.new(rel.outputs["Color"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    # city lights where the surface faces away from the sun
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sv = nt.nodes.new("ShaderNodeCombineXYZ")
    sv.inputs[0].default_value, sv.inputs[1].default_value, sv.inputs[2].default_value = sun_v
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(geo.outputs["Normal"], dot.inputs[0])
    nt.links.new(sv.outputs[0], dot.inputs[1])
    night = nt.nodes.new("ShaderNodeMapRange")
    night.inputs["From Min"].default_value, night.inputs["From Max"].default_value = 0.02, -0.18
    nt.links.new(dot.outputs["Value"], night.inputs["Value"])
    lights = nt.nodes.new("ShaderNodeMath")
    lights.operation, lights.inputs[1].default_value = "MULTIPLY", 2.6
    nt.links.new(night.outputs["Result"], lights.inputs[0])
    nt.links.new(ngt.outputs["Color"], b.inputs["Emission Color"])
    nt.links.new(lights.outputs[0], b.inputs["Emission Strength"])
    e.data.materials.append(m)
    parts.append(e)
    # clouds: their own shell, alpha from layered noise, casting shadows on the land
    bpy.ops.mesh.primitive_uv_sphere_add(segments=384, ring_count=192, radius=radius * 1.006, location=centre)
    c = bpy.context.active_object
    c.name = name + "_clouds"
    c.rotation_euler = e.rotation_euler
    for pg in c.data.polygons:
        pg.use_smooth = True
    cm = bpy.data.materials.new(name + "_clouds")
    cm.use_nodes = True
    cn = cm.node_tree
    cb = cn.nodes["Principled BSDF"]
    cb.inputs["Base Color"].default_value = (*hex_lin("#f6f7f9"), 1)
    cb.inputs["Roughness"].default_value = 0.9
    tc = cn.nodes.new("ShaderNodeTexCoord")
    n1 = cn.nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 3.2
    n1.inputs["Detail"].default_value = 14
    n1.inputs["Roughness"].default_value = 0.58
    n1.inputs["Distortion"].default_value = 0.55
    cn.links.new(tc.outputs["Generated"], n1.inputs["Vector"])
    n2 = cn.nodes.new("ShaderNodeTexNoise")
    n2.inputs["Scale"].default_value = 22.0
    n2.inputs["Detail"].default_value = 8
    cn.links.new(tc.outputs["Generated"], n2.inputs["Vector"])
    mix = cn.nodes.new("ShaderNodeMath")
    mix.operation = "MULTIPLY_ADD"
    cn.links.new(n2.outputs["Fac"], mix.inputs[0])
    mix.inputs[1].default_value = 0.25
    cn.links.new(n1.outputs["Fac"], mix.inputs[2])
    cov = cn.nodes.new("ShaderNodeMapRange")                         # about a third of the sky clouded
    cov.inputs["From Min"].default_value, cov.inputs["From Max"].default_value = 0.66, 0.82
    cn.links.new(mix.outputs[0], cov.inputs["Value"])
    cn.links.new(cov.outputs["Result"], cb.inputs["Alpha"])
    c.data.materials.append(cm)
    parts.append(c)
    # the atmosphere: a thin blue glow at the limb
    bpy.ops.mesh.primitive_uv_sphere_add(segments=256, ring_count=128, radius=radius * 1.018, location=centre)
    a = bpy.context.active_object
    a.name = name + "_air"
    for pg in a.data.polygons:
        pg.use_smooth = True
    am = bpy.data.materials.new(name + "_air")
    am.use_nodes = True
    an = am.node_tree
    for n in list(an.nodes):
        if n.type != "OUTPUT_MATERIAL":
            an.nodes.remove(n)
    lw = an.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.25
    pw = an.nodes.new("ShaderNodeMath")
    pw.operation, pw.inputs[1].default_value = "POWER", 4.0
    an.links.new(lw.outputs["Facing"], pw.inputs[0])
    em = an.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*hex_lin("#5f9dff"), 1)
    em.inputs["Strength"].default_value = 4.0
    tr = an.nodes.new("ShaderNodeBsdfTransparent")
    mx = an.nodes.new("ShaderNodeMixShader")
    an.links.new(pw.outputs[0], mx.inputs["Fac"])
    an.links.new(tr.outputs[0], mx.inputs[1])
    an.links.new(em.outputs[0], mx.inputs[2])
    an.links.new(mx.outputs[0], an.nodes["Material Output"].inputs["Surface"])
    a.data.materials.append(am)
    a.visible_shadow = False
    parts.append(a)
    ld = bpy.data.lights.new(name + "_sun", "SUN")
    ld.energy, ld.color, ld.angle = 4.5, hex_lin("#fff6ea"), math.radians(0.53)
    sun = bpy.data.objects.new(name + "_sun", ld)
    bpy.context.scene.collection.objects.link(sun)
    sun.rotation_euler = (-sun_v).to_track_quat("-Z", "Y").to_euler()
    link_lights([sun], parts, name + "_lit")
    return e


def limb_centre(eye, through, distance, radius, sideways=0.3):
    """Where the Earth's centre goes so its limb passes through a point of the view: the sight line from
    the eye through `through` grazes the sphere `distance` metres out. `sideways` tilts the limb."""
    c = Vector(eye)
    d = (Vector(through) - c).normalized()
    down = Vector((sideways, 0.0, -1.0))
    n = (down - d * down.dot(d)).normalized()
    return tuple(c + d * distance + n * radius)


def stars(bulbs, n=2500, dist=400.0, seed=19, occluders=(), eye=(0.0, -2.95, 1.43)):
    """Round stars: tiny glowing points over the sky ahead, at three sizes. None where a planet and its
    atmosphere stand in front (a star showing through the Earth's glow gives the trick away)."""
    rng = np.random.default_rng(seed)
    groups = {0: [], 1: [], 2: []}
    for _ in range(n):
        v = rng.normal(size=3)
        v[1] = abs(v[1]) + 0.3                          # ahead of the camera, through the opening
        v /= np.linalg.norm(v)
        k = int(rng.choice(3, p=(0.75, 0.2, 0.05)))
        p = v * dist
        hidden = False
        for (oc, orad) in occluders:
            d = p - np.array(eye)
            d /= np.linalg.norm(d)
            w = np.array(oc) - np.array(eye)
            t = w.dot(d)
            if t > 0 and np.linalg.norm(w - d * t) < orad:
                hidden = True
        if not hidden:
            groups[k].append(tuple(p))
    for k, (r, strength) in enumerate(((0.16, 14.0), (0.24, 26.0), (0.36, 45.0))):
        bulbs(f"stars_{k}", groups[k], "#e6ecff", strength, r=r)
