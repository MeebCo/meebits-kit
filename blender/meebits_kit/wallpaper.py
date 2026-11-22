"""iPhone spatial Lock Screen wallpapers of any Meebit.

iOS 26 can turn a flat Lock Screen photo into a spatial scene: it finds the subject, cuts it out, puts the
clock between the subject and the background, and shifts the layers as the phone tilts. It works out the
depth by itself, so the picture has to separate cleanly on its own. Everything here is tuned for that, and
measured on an iPhone 17 Pro:

- iOS shows the wallpaper zoomed 1.15x about its centre. The clock digits then sit 18.3% to 26.9% of the
  wallpaper from the top, and the flashlight and camera buttons are centred 91% down the screen.
- If the subject covers much of the digits (around 60%), iOS gives up and puts the clock in front of it.
  The top of the Meebit lands 25.4% from the top, so it overlaps the digits by about 17%.
- The feet stay 18.8% from the bottom, clear of the buttons after the zoom.
- iOS renders the cut-out subject much softer than the background. A 1320 x 2868 file looked blurry on
  the phone; the same render at 2x (2640 x 5736) looked sharp. So the phone file is the 2x render.
- The outline has to stand out from what's behind it, or the cut-out comes out ragged.

    from meebits_kit import wallpaper
    wallpaper.make(8506, "capsule", "renders")      # writes the master, the phone file, a mask, a report
"""
import json
import math
import os
import time

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

from . import core, earth

SCENES = {
    "capsule": "A white space capsule with its hatch open onto a close, detailed Earth",
    "giftbox": "Standing in an opened Christmas present, its back folded down, in a green living room with a lit tree",
}
W, H = 1320, 2868                 # the iPhone 17 Pro Max screen; it fits the 17 Pro too
TOP, FEET = 0.254, 0.188          # top of the Meebit from the top, feet from the bottom, as frame heights
VFOV = 58.0                       # vertical field of view, degrees
EYE_LEVEL = 0.84                  # camera height as a share of the Meebit's height: its eyes, straight on


# ---------- small builders ----------
def hex_lin(h):
    h = h.lstrip("#")
    return tuple((c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
                 for c in (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)))


def obj(name, data, m=None, loc=(0, 0, 0)):
    o = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    if m is not None:
        o.data.materials.append(m)
    return o


def mesh(name, verts, faces, m=None, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    for p in me.polygons:
        p.use_smooth = smooth
    return obj(name, me, m)


def cube(name, lo, hi, m, bevel=0.0):
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    o = mesh(name, v, f, m)
    if bevel:
        b = o.modifiers.new("bevel", "BEVEL")
        b.width, b.segments, b.limit_method = bevel, 2, "ANGLE"
    return o


def mat(name, hexc, rough=0.5, bump=0.0, scale=5.0, var=0.0, tiles=None, tile_line="#000000", metallic=0.0,
        coat=0.0, mortar=0.012):
    """A plain material. var: a soft tonal variation. tiles: (w, h) in metres for floor slabs."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    base = hex_lin(hexc)
    bsdf.inputs["Base Color"].default_value = (*base, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metallic
    if coat:
        bsdf.inputs["Coat Weight"].default_value = coat
    tc = nt.nodes.new("ShaderNodeTexCoord")
    colour = None
    if var:
        n2 = nt.nodes.new("ShaderNodeTexNoise")
        n2.inputs["Scale"].default_value = scale * 0.3
        n2.inputs["Detail"].default_value = 6
        nt.links.new(tc.outputs["Object"], n2.inputs["Vector"])
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (*[c * (1 - var) for c in base], 1)
        ramp.color_ramp.elements[1].color = (*[min(1, c * (1 + var)) for c in base], 1)
        nt.links.new(n2.outputs["Fac"], ramp.inputs["Fac"])
        colour = ramp.outputs["Color"]
    if tiles:
        br = nt.nodes.new("ShaderNodeTexBrick")
        mp = nt.nodes.new("ShaderNodeMapping")
        nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
        mp.inputs["Scale"].default_value = (1 / tiles[0], 1 / tiles[1], 1)
        br.inputs["Scale"].default_value = 1.0
        br.inputs["Brick Width"].default_value = 1.0
        br.inputs["Row Height"].default_value = 1.0
        br.inputs["Mortar Size"].default_value = mortar
        br.offset = 0.5
        br.inputs["Color1"].default_value = (*[c * 0.96 for c in base], 1)
        br.inputs["Color2"].default_value = (*[min(1, c * 1.04) for c in base], 1)
        br.inputs["Mortar"].default_value = (*hex_lin(tile_line), 1)
        nt.links.new(mp.outputs["Vector"], br.inputs["Vector"])
        if colour is not None:
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type, mix.blend_type = "RGBA", "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0
            nt.links.new(br.outputs["Color"], mix.inputs["A"])
            nt.links.new(colour, mix.inputs["B"])
            gain = nt.nodes.new("ShaderNodeMix")          # multiplying two base-coloured terms darkens
            gain.data_type, gain.blend_type = "RGBA", "DIVIDE"
            gain.inputs["Factor"].default_value = 1.0
            nt.links.new(mix.outputs["Result"], gain.inputs["A"])
            gain.inputs["B"].default_value = (*base, 1)
            colour = gain.outputs["Result"]
        else:
            colour = br.outputs["Color"]
    if colour is not None:
        nt.links.new(colour, bsdf.inputs["Base Color"])
    if bump:
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = scale
        noise.inputs["Detail"].default_value = 8
        nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
        bp = nt.nodes.new("ShaderNodeBump")
        bp.inputs["Strength"].default_value = bump
        nt.links.new(noise.outputs["Fac"], bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def emit(name, hexc, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*hex_lin(hexc), 1)
    e.inputs["Strength"].default_value = strength
    nt.links.new(e.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    return m


def area(name, loc, aim, size, energy, hexc="#fff4e6", sy=None):
    """A soft light the camera never sees, and that nothing mirrors unless asked."""
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy, ld.color = energy, hex_lin(hexc)
    if sy:
        ld.shape, ld.size, ld.size_y = "RECTANGLE", size, sy
    else:
        ld.size = size
    o = obj(name, ld, loc=loc)
    o.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    o.visible_camera = o.visible_glossy = o.visible_transmission = False
    return o


def spot(name, loc, aim, energy, cone=30.0, blend=0.4, hexc="#fff1dc", radius=0.05):
    ld = bpy.data.lights.new(name, "SPOT")
    ld.energy, ld.color, ld.spot_size, ld.spot_blend, ld.shadow_soft_size = (
        energy, hex_lin(hexc), math.radians(cone), blend, radius)
    o = obj(name, ld, loc=loc)
    o.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


def world(hexc, strength):
    w = bpy.data.worlds.new("wallpaper")
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*hex_lin(hexc), 1)
    bg.inputs["Strength"].default_value = strength
    bpy.context.scene.world = w


def link_lights(lights, objs, name):
    """Light linking: these lights reach only these objects."""
    c = bpy.data.collections.new(name)
    for o in objs:
        c.objects.link(o)
    for lo in lights:
        lo.light_linking.receiver_collection = c
    for co in c.collection_objects:
        co.light_linking.link_state = "INCLUDE"
    return c


def _boxes(name, centres, r, m):
    verts, faces = [], []
    for (x, y, z) in centres:
        i = len(verts)
        for dx in (-r, r):
            for dy in (-r, r):
                for dz in (-r, r):
                    verts.append((x + dx, y + dy, z + dz))
        faces += [(i, i + 1, i + 3, i + 2), (i + 4, i + 6, i + 7, i + 5), (i, i + 4, i + 5, i + 1),
                  (i + 2, i + 3, i + 7, i + 6), (i, i + 2, i + 6, i + 4), (i + 1, i + 5, i + 7, i + 3)]
    return mesh(name, verts, faces, m)


def bulbs(name, pts, hexc, strength, r=0.025):
    """Small glowing cubes as one mesh: fairy lights, snow, stars. Out of focus they read as round."""
    return _boxes(name, pts, r, emit(name + "_glow", hexc, strength))


def cubes(name, centres, size, m):
    return _boxes(name, centres, size / 2, m)


def glossy_white(name, hexc="#f1f1ee", rough=0.18):
    """Bright, shiny white panels: a light base, low roughness and a clear coat, so light strips streak in it."""
    m = mat(name, hexc, rough=rough, var=0.02, scale=2.0, coat=1.0)
    m.node_tree.nodes["Principled BSDF"].inputs["Coat Roughness"].default_value = 0.04
    return m


def chrome(name, hexc="#d9dde2", rough=0.08):
    return mat(name, hexc, rough=rough, metallic=1.0)


def satin(name, hexc, rough=0.3, sheen=0.5, coat=0.5):
    """Satin ribbon and gilt: not a metal, so it keeps its colour in a dark room instead of mirroring the dark."""
    m = mat(name, hexc, rough=rough, coat=coat)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Sheen Weight"].default_value = sheen
    b.inputs["Sheen Tint"].default_value = (*hex_lin("#fff1c8"), 1)
    return m


def giftpaper(name, base, stripe, width=0.15, gap=0.075, rough=0.65, foil_rough=0.25):
    """Wrapping paper: a matte base with a fibre bump and thin diagonal foil pinstripes. Only the foil is
    metallic and smooth, so it flashes."""
    m = mat(name, base, rough=rough, var=0.04, scale=4.0, bump=0.02)
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    nt.links.new(sep.outputs["X"], add.inputs[0])
    nt.links.new(sep.outputs["Y"], add.inputs[1])
    add2 = nt.nodes.new("ShaderNodeMath")
    add2.operation = "ADD"
    nt.links.new(add.outputs[0], add2.inputs[0])
    nt.links.new(sep.outputs["Z"], add2.inputs[1])
    mod = nt.nodes.new("ShaderNodeMath")
    mod.operation = "FLOORED_MODULO"
    mod.inputs[1].default_value = gap
    nt.links.new(add2.outputs[0], mod.inputs[0])
    lt = nt.nodes.new("ShaderNodeMath")
    lt.operation = "LESS_THAN"
    lt.inputs[1].default_value = width * gap
    nt.links.new(mod.outputs[0], lt.inputs[0])
    cmix = nt.nodes.new("ShaderNodeMix")
    cmix.data_type = "RGBA"
    old = b.inputs["Base Color"].links[0].from_socket if b.inputs["Base Color"].links else None
    if old is not None:
        nt.links.new(old, cmix.inputs["A"])
    else:
        cmix.inputs["A"].default_value = (*hex_lin(base), 1)
    cmix.inputs["B"].default_value = (*hex_lin(stripe), 1)
    nt.links.new(lt.outputs[0], cmix.inputs["Factor"])
    nt.links.new(cmix.outputs["Result"], b.inputs["Base Color"])
    nt.links.new(lt.outputs[0], b.inputs["Metallic"])
    rmix = nt.nodes.new("ShaderNodeMath")
    rmix.operation = "MULTIPLY_ADD"
    nt.links.new(lt.outputs[0], rmix.inputs[0])
    rmix.inputs[1].default_value = foil_rough - rough
    rmix.inputs[2].default_value = rough
    nt.links.new(rmix.outputs[0], b.inputs["Roughness"])
    return m


def ribbon_strip(name, pts2d, width, m, cyclic=False):
    """A satin band along a 2D path in the x-z plane, its width running front to back."""
    cd = bpy.data.curves.new(name, "CURVE")
    cd.dimensions = "2D"
    cd.extrude = width / 2
    sp = cd.splines.new("POLY")
    sp.points.add(len(pts2d) - 1)
    for p, (x, z) in zip(sp.points, pts2d):
        p.co = (x, z, 0.0, 1.0)
    sp.use_cyclic_u = cyclic
    o = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(o)
    o.data.materials.append(m)
    o.rotation_euler = (math.radians(90), 0, 0)
    o.modifiers.new("thick", "SOLIDIFY").thickness = 0.004
    o.modifiers.new("smooth", "WEIGHTED_NORMAL")
    cd.resolution_u = 12
    return o


def bow(m, at, size=0.19, width=0.1):
    """A gift bow on a box rim: two big teardrop loops and two smaller ones, tipped back so the satin shows,
    a wrapped knot, and two tails falling inside the box."""
    x0, y0, z0 = at
    objs = []
    c24, s24 = math.cos(math.radians(24)), math.sin(math.radians(24))
    for k in (-1, 1):
        for j, (sc, tilt, w) in enumerate(((1.0, 29, width), (0.62, 47, width * 0.85))):
            a = size / 2 * sc
            pts = []
            for i in range(56):
                u = math.pi + 2 * math.pi * i / 56
                lx, lz = a + a * math.cos(u), 0.62 * a * math.sin(u)
                lz *= (lx / (2 * a)) ** 0.35
                pts.append((k * (lx * c24 - lz * s24), lx * s24 + lz * c24))
            o = ribbon_strip(f"bow_loop_{k}_{j}", pts, w, m, cyclic=True)
            o.location = (x0, y0 - 0.005 * j, z0 + 0.045)
            o.rotation_euler = (math.radians(tilt), 0, math.radians(-k * 14))
            objs.append(o)
    for k in (-1, 1):
        pts = [(0.0, 0.0), (-0.035, -0.07), (-0.05, -0.17), (-0.05 - 0.02 * k, -0.30 - 0.04 * k)]
        o = ribbon_strip(f"bow_tail_{k}", pts, width * 0.85, m)
        o.location = (x0 - 0.085 + k * 0.022, y0 - 0.03, z0 + 0.03)
        o.rotation_euler = (math.radians(90), 0, math.radians(90 + k * 12))
        objs.append(o)
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.038, depth=0.09, location=(x0, y0 - 0.01, z0 + 0.035),
                                        rotation=(0, math.radians(90), 0))
    kn = bpy.context.active_object
    kn.name = "bow_knot"
    kn.scale = (1.0, 1.15, 0.85)
    kn.modifiers.new("bevel", "BEVEL").width = 0.012
    kn.data.materials.append(m)
    for pg in kn.data.polygons:
        pg.use_smooth = True
    return objs + [kn]


# ---------- the scenes ----------
# Each builds the set around a Meebit standing at the origin, facing the camera (-Y), and returns how to
# light it: the floor height, key and rim, depth of field, and which objects the key may light.

def capsule():
    """A sleek white space capsule: glossy curved panels, chrome ribs, light strips, consoles, and a dark
    walkway so white shoes stand out. The rear hatch is open onto black space and a huge, close Earth whose
    limb arcs behind the Meebit's chest. The space behind the clock stays black, so a white clock reads."""
    y0, yb, R, cz = -6.0, 1.6, 1.9, 1.2                # the rear bulkhead 1.6 m behind the Meebit
    wall = glossy_white("cap_wall")
    seam = mat("cap_seam", "#b9bcc0", rough=0.4)
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=R, depth=yb - y0, location=(0, (y0 + yb) / 2, cz),
                                        rotation=(math.pi / 2, 0, 0), end_fill_type="NOTHING")
    shell = bpy.context.active_object
    shell.name = "cap_shell"
    for pg in shell.data.polygons:
        pg.use_smooth = True
    shell.data.materials.append(wall)
    hw = math.sqrt(R * R - cz * cz)
    cube("cap_floor", (-hw - 0.05, y0, -0.04), (hw + 0.05, yb, 0.0), glossy_white("cap_floor_m", "#e9e9e6", rough=0.22))
    cube("cap_walk", (-0.55, y0, 0.0), (0.55, yb, 0.004), mat("cap_walk_m", "#2a2e34", rough=0.35, coat=0.5,
                                                             tiles=(0.55, 0.55), tile_line="#15181c", mortar=0.01))
    for x in (-0.9, -0.45, 0.45, 0.9):
        cube(f"cap_fseam_{x}", (x - 0.004, y0, 0.0), (x + 0.004, yb, 0.001), seam)
    ribm = chrome("cap_rib")
    for i, y in enumerate(np.arange(y0 + 0.3, yb, 0.75)):
        bpy.ops.mesh.primitive_torus_add(major_radius=R - 0.03, minor_radius=0.028, major_segments=96,
                                         minor_segments=12, location=(0, y, cz), rotation=(math.pi / 2, 0, 0))
        t = bpy.context.active_object
        t.name = f"cap_rib_{i}"
        t.data.materials.append(ribm)
        for pg in t.data.polygons:
            pg.use_smooth = True
    strip = emit("cap_strip", "#f4f7ff", 3.0)
    for s in (-1, 1):
        ang = math.radians(52)
        o = cube(f"cap_strip_{s}", (-0.025, y0, -0.02), (0.025, yb, 0.02), strip)
        o.location = (s * (R - 0.04) * math.sin(ang), 0, cz + (R - 0.04) * math.cos(ang))
        o.rotation_euler = (0, -s * ang, 0)
    white = glossy_white("bulkhead")
    brushed = chrome("brushed", "#c4c8cc", rough=0.28)
    for s in (-1, 1):                                    # consoles along the walls, small glowing panels
        cube(f"console_{s}", (s * (hw - 0.05) - 0.18 * (s > 0), -1.2, 0), (s * (hw - 0.05) + 0.18 * (s < 0), 0.9, 0.85),
             white, bevel=0.03)
        cube(f"console_top_{s}", (s * (hw - 0.05) - 0.2 * (s > 0), -1.22, 0.85),
             (s * (hw - 0.05) + 0.2 * (s < 0), 0.92, 0.88), brushed, bevel=0.01)
        for j, y in enumerate(np.arange(-1.0, 0.8, 0.45)):
            x = s * (hw - 0.05) + (-0.12 if s > 0 else 0.12)
            cube(f"panel_{s}_{j}", (x - 0.06, y, 0.89), (x + 0.06, y + 0.25, 0.9),
                 emit(f"panel_glow_{s}_{j}", ["#7fd4ff", "#a8ffcf", "#ffd59a"][j % 3], 2.5))
    # the rear bulkhead with the open hatch, a chrome ring and bolts, the door swung open inside
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=R, depth=0.12, location=(0, yb + 0.06, cz),
                                        rotation=(math.pi / 2, 0, 0))
    bh = bpy.context.active_object
    bh.name = "bulkhead"
    bh.data.materials.append(white)
    wr, wz = 1.35, 1.65
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=wr, depth=0.5, location=(0, yb + 0.06, wz),
                                        rotation=(math.pi / 2, 0, 0))
    cut = bpy.context.active_object
    bm = bh.modifiers.new("opening", "BOOLEAN")
    bm.operation, bm.object, bm.solver = "DIFFERENCE", cut, "EXACT"
    cut.hide_render = cut.hide_viewport = True
    bpy.ops.mesh.primitive_torus_add(major_radius=wr + 0.03, minor_radius=0.06, major_segments=96, minor_segments=16,
                                     location=(0, yb, wz), rotation=(math.pi / 2, 0, 0))
    ring = bpy.context.active_object
    ring.name = "opening_ring"
    ring.data.materials.append(chrome("trim"))
    for pg in ring.data.polygons:
        pg.use_smooth = True
    for k in range(12):
        a = 2 * math.pi * k / 12
        cube(f"bolt_{k}", (-0.02, -0.02, -0.02), (0.02, 0.02, 0.02), brushed).location = (
            (wr + 0.13) * math.cos(a), yb - 0.01, wz + (wr + 0.13) * math.sin(a))
    door = cube("hatch_door", (0, -0.08, -wr), (2 * wr, 0.0, wr), white, bevel=0.03)
    door.location = (wr * 0.9, yb - 0.1, wz)
    door.rotation_euler = (0, 0, math.radians(-70))
    world("#020306", 1.0)
    # outside: the Earth, close and huge (the sight line through the hatch at 1.2 m grazes it 120 m out)
    centre = earth.limb_centre((0.0, -2.95, 1.43), (0.0, yb, 1.2), 120.0, 90.0, sideways=0.35)
    earth.stars(bulbs, occluders=[(centre, 90.0 * 1.03)])
    earth.earth("earth", centre, 90.0, link_lights=link_lights, hex_lin=hex_lin)
    # soft fill that keeps the whites bright without flattening the Meebit
    area("cap_fill_top", (0.0, -0.5, 2.9), (0.0, -0.5, 0.0), 2.4, 110.0, "#f6f8ff", sy=1.4)
    area("cap_fill_back", (0.0, -4.5, 1.6), (0.0, 0.0, 1.0), 2.0, 50.0, "#f6f8ff")
    return {"floor_z": 0.0, "key": ((-1.1, -1.5, 2.3), 85.0, 0.7), "rim": ((1.2, -1.0, 1.9), 12.0),
            "fstop": 8.0, "fill": 8.0, "card": 1.0, "coat": 0.45,
            "key_receivers": ["cap_floor", "cap_walk"]}   # no key light mirrored in the glossy walls


def giftbox():
    """Standing in an opened Christmas present: the front and back flaps folded down flat, matte red paper
    with gold foil pinstripes inside and out, gilt rims, a gold satin ribbon and a full bow on the right rim.
    Behind: wrapped presents, a dark green panelled living room, a stepped voxel tree with baubles and lights,
    fairy lights, and a snowy night window to the right of the clock."""
    bx, by0, by1, bh, t, base_t = 0.62, -0.55, 0.75, 1.0, 0.025, 0.03
    paper = giftpaper("gift_paper", "#8c363d", "#b38a3e", width=0.10)
    lining = giftpaper("gift_lining", "#7f323a", "#a8823c", width=0.10)
    ribbon = satin("ribbon", "#c8962f", rough=0.28, sheen=0.8, coat=0.6)
    gilt = satin("gilt", "#d4ae5c", rough=0.25, sheen=0.3, coat=0.6)
    cube("box_base", (-bx - t, by0, 0), (bx + t, by1 + t, base_t), paper)
    cube("box_floor_lining", (-bx, by0, base_t), (bx, by1, base_t + 0.002), lining)
    for s in (-1, 1):
        x_out, x_in = s * (bx + t), s * bx
        cube(f"wall_{s}", (min(x_out, x_in), by0, 0), (max(x_out, x_in), by1 + t, bh), paper)
        cube(f"lining_{s}", (min(x_in, x_in - s * 0.003), by0, base_t), (max(x_in, x_in - s * 0.003), by1, bh), lining)
        cube(f"rim_{s}", (min(x_out, x_in - s * 0.003) - 0.001, by0, bh),
             (max(x_out, x_in - s * 0.003) + 0.001, by1 + t, bh + 0.004), gilt)
    # the back wall folded down flat behind the Meebit, lining up, like the front flap: the room shows behind
    # its whole body, which gives iOS a clear depth jump all the way down
    lining_back = cube("back_flap", (-bx - t, by1, 0), (bx + t, by1 + 1.0, t), lining)
    cube("back_flap_paper", (-bx - t, by1, -0.001), (bx + t, by1 + 1.0, 0.0005), paper)
    cube("flap", (-bx - t, by0 - bh, 0), (bx + t, by0, t), lining)
    cube("flap_paper_edge", (-bx - t, by0 - bh, -0.001), (bx + t, by0, 0.0005), paper)
    rw, ry = 0.09, by1 - 0.08                           # the ribbon over the side walls, down inside
    rib = []
    for s in (-1, 1):
        x_out, x_in = s * (bx + t + 0.002), s * (bx - 0.003)
        rib.append(cube(f"rib_out_{s}", (min(x_out, x_out - s * 0.004), ry - rw / 2, 0),
                        (max(x_out, x_out - s * 0.004), ry + rw / 2, bh + 0.006), ribbon))
        rib.append(cube(f"rib_top_{s}", (min(x_out, x_in), ry - rw / 2, bh + 0.004),
                        (max(x_out, x_in), ry + rw / 2, bh + 0.008), ribbon))
        rib.append(cube(f"rib_in_{s}", (min(x_in, x_in - s * 0.004), ry - rw / 2, base_t + 0.002),
                        (max(x_in, x_in - s * 0.004), ry + rw / 2, bh + 0.006), ribbon))
    xr = 0.615                                          # the band runs out along the folded flap; the bow on the side rim
    rib.append(cube("rib_back_flap", (xr - rw / 2, by1, t), (xr + rw / 2, by1 + 1.0, t + 0.004), ribbon))
    bow_at = (bx + t / 2, ry, bh + 0.008)
    rib += bow(ribbon, bow_at, size=0.15)
    bow_light = area("bow_light", (0.15, -0.7, 1.9), (bow_at[0], bow_at[1], bh + 0.1), 0.5, 14.0, "#fff4e0")
    bow_light.visible_glossy = True                     # a sheen streak on the satin
    link_lights([bow_light], rib, "bow_receivers")
    lb = area("lining_light", (0.0, -0.3, 0.12), (0.0, 1.3, 0.0), 1.2, 30.0, "#fff2ea", sy=0.3)
    link_lights([lb], [lining_back], "lining_receivers")   # the folded flap lit, so dark trousers separate
    # the room: dark green walls panelled full height with gilt beads, a wood floor
    rx, ry1, rh = 3.2, 5.0, 6.6
    cube("room_floor", (-rx, -4.0, -0.04), (rx, ry1, 0.0),
         mat("room_floor", "#5a3a26", rough=0.4, var=0.15, tiles=(0.18, 1.6), tile_line="#2a1a10", mortar=0.006))
    green = mat("room_wall", "#2a4a3a", rough=0.75, var=0.06, scale=1.0)
    panel = mat("room_panel", "#33584a", rough=0.6, var=0.05, scale=1.0)
    back = cube("room_back", (-rx, ry1, 0), (rx, ry1 + 0.1, rh), green)
    cube("room_L", (-rx - 0.1, -4.0, 0), (-rx, ry1, rh), green)
    cube("room_R", (rx, -4.0, 0), (rx + 0.1, ry1, rh), green)
    cube("room_ceiling", (-rx, -4.0, rh), (rx, ry1, rh + 0.1), mat("room_ceiling", "#3a3229", rough=0.9))
    bead = satin("gilt_bead", "#c9a250", rough=0.3, sheen=0.2, coat=0.4)
    cube("skirting", (-rx, ry1 - 0.03, 0), (rx, ry1, 0.16), mat("trim", "#e8dfcf", rough=0.5))
    for i, z in enumerate((1.0, 1.9, 6.2)):              # rails placed off the Meebit's head and shoulders
        cube(f"rail_{i}", (-rx, ry1 - 0.03, z - 0.05), (rx, ry1, z + 0.05), panel)
        cube(f"bead_{i}", (-rx, ry1 - 0.035, z + 0.05), (rx, ry1 - 0.005, z + 0.062), bead)
    for i, x in enumerate((-2.85, -1.95, -1.05, 1.05, 1.95, 2.85)):   # the centre panel frames the clock
        cube(f"stile_{i}", (x - 0.035, ry1 - 0.028, 0.16), (x + 0.035, ry1, rh), panel)
    # a tall night window right of the clock: navy, falling snow, a snowy street
    wx0, wx1, wz0, wz1 = 1.25, 2.0, 1.8, 4.4
    sky = emit("night_sky", "#0b1530", 0.9)
    hole = cube("window_hole", (wx0, ry1 - 0.2, wz0), (wx1, ry1 + 0.3, wz1), sky)
    bm = back.modifiers.new("window", "BOOLEAN")
    bm.operation, bm.object, bm.solver = "DIFFERENCE", hole, "EXACT"
    hole.hide_render = hole.hide_viewport = True
    cube("night_sky", (-30, 22.0, -5), (30, 22.2, 30), sky)
    roofs = mat("roofs", "#141c33", rough=0.9)
    snowcap = mat("snowcap", "#c8d4ec", rough=0.8)
    houses = [(0.6, 3.0, 5.0), (3.6, 2.6, 6.2), (6.4, 3.4, 4.6), (-2.4, 3.0, 5.6)]
    lit, rng_w = [], np.random.default_rng(25)
    for i, (x, w, h) in enumerate(houses):
        cube(f"house_{i}", (x, 15.0, 0), (x + w, 17.0, h), roofs)
        cube(f"house_snow_{i}", (x - 0.1, 14.9, h), (x + w + 0.1, 17.1, h + 0.25), snowcap)
        for fx in np.arange(x + 0.4, x + w - 0.3, 0.8):
            for fz in np.arange(3.2, h - 0.4, 1.1):
                if rng_w.random() < 0.6:
                    lit.append((fx, 14.97, fz))
    cubes("street_windows", lit, 0.3, emit("street_glow", "#ffc070", 3.0))
    for nm, lo, hi in [("win_L", (wx0 - 0.07, ry1 - 0.08, wz0 - 0.07), (wx0, ry1 - 0.03, wz1 + 0.07)),
                       ("win_R", (wx1, ry1 - 0.08, wz0 - 0.07), (wx1 + 0.07, ry1 - 0.03, wz1 + 0.07)),
                       ("win_T", (wx0 - 0.07, ry1 - 0.08, wz1), (wx1 + 0.07, ry1 - 0.03, wz1 + 0.07)),
                       ("win_sill", (wx0 - 0.12, ry1 - 0.16, wz0 - 0.1), (wx1 + 0.12, ry1 - 0.03, wz0)),
                       ("win_mull", ((wx0 + wx1) / 2 - 0.02, ry1 - 0.07, wz0), ((wx0 + wx1) / 2 + 0.02, ry1 - 0.035, wz1)),
                       ("win_bar", (wx0, ry1 - 0.07, (wz0 + wz1) / 2 - 0.02), (wx1, ry1 - 0.035, (wz0 + wz1) / 2 + 0.02))]:
        cube(nm, lo, hi, panel)                         # the frame in the wall's own green: the window stays quiet
    cube("win_gilt", (wx0 - 0.075, ry1 - 0.085, wz1 + 0.07), (wx1 + 0.075, ry1 - 0.03, wz1 + 0.08), bead)
    rng = np.random.default_rng(8506)
    for j, (rr, st, n) in enumerate(((0.01, 0.8, 140), (0.018, 0.6, 100), (0.028, 0.45, 60))):   # snow at depth
        snow = []
        for _ in range(n):
            y = rng.uniform(5.3, 14.0)
            k = (y + 2.65) / (ry1 + 2.65)                # wider with distance, to fill the window's view
            snow.append((rng.uniform(wx0 - 0.1, wx1 + 0.6) * k, y, rng.uniform(wz0 - 0.4, wz1 + 0.6) * k))
        bulbs(f"snow_{j}", snow, "#dfe8ff", st, r=rr)
    # the tree: stepped voxel tiers in deep spruce, red and gold baubles, warm bulbs, a gold voxel star
    tree = mat("tree", "#10291a", rough=0.85, var=0.2, bump=0.3, scale=14.0)
    tx, ty, tiers = -1.6, 3.2, 7
    bulb_pts, red_pts, gold_pts = [], [], []
    for i in range(tiers):
        hw = 0.68 * (1 - i / tiers) + 0.08
        z0 = 0.3 + i * 0.4
        tier = cube(f"tree_{i}", (-hw, -hw, 0), (hw, hw, 0.4), tree, bevel=0.01)
        tier.location = (tx, ty, z0)
        tier.rotation_euler = (0, 0, math.radians(45 * (i % 2)))
        ca, sa = math.cos(math.radians(45 * (i % 2))), math.sin(math.radians(45 * (i % 2)))
        for _ in range(int(90 * hw) + 6):
            side = rng.integers(4)
            u = rng.uniform(-hw, hw)
            p = [(u, -hw - 0.02), (hw + 0.02, u), (u, hw + 0.02), (-hw - 0.02, u)][side]
            p = (tx + p[0] * ca - p[1] * sa, ty + p[0] * sa + p[1] * ca)
            [bulb_pts, red_pts, gold_pts][rng.integers(3)].append((p[0], p[1], z0 + rng.uniform(0.05, 0.35)))
    cube("tree_trunk", (tx - 0.09, ty - 0.09, 0), (tx + 0.09, ty + 0.09, 0.3), mat("trunk", "#3b2618", rough=0.9))
    bulbs("tree_lights", bulb_pts, "#ffc77a", 30.0, r=0.016)
    cubes("baubles_red", red_pts, 0.07, satin("bauble_red", "#a01828", rough=0.2, sheen=0.1, coat=1.0))
    cubes("baubles_gold", gold_pts, 0.07, satin("bauble_gold", "#d8b25a", rough=0.2, sheen=0.1, coat=1.0))
    top = 0.3 + tiers * 0.4
    star = [(tx, ty, top + 0.12)] + [(tx + dx, ty, top + 0.12 + dz) for dx, dz in ((0.08, 0), (-0.08, 0), (0, 0.08), (0, -0.08))]
    cubes("star", star, 0.08, emit("star_glow", "#ffd27a", 4.0))
    for j, (zt, sag) in enumerate([(3.0, 0.25), (2.4, 0.25)]):   # fairy lights across the window side
        p = []
        x0, x1 = 1.28, rx - 0.15
        for k in range(36):
            u = k / 35
            seg = (u * 2) % 1.0
            p.append((x0 + u * (x1 - x0), ry1 - 0.06, zt - sag * 4 * seg * (1 - seg)))
        bulbs(f"strand_{j}", p, "#ffd08a", 9.0, r=0.016)
    area("tree_glow", (tx + 0.6, ty - 1.0, 1.2), (tx, ty, 1.2), 1.0, 45.0, "#ffb866")
    tspot = spot("tree_spot", (-0.4, 1.6, 3.2), (tx, ty, 2.0), 160.0, cone=35, blend=0.6, hexc="#ffd9a0", radius=0.2)
    link_lights([tspot], [o for o in bpy.context.scene.objects
                          if o.type == "MESH" and o.name.startswith(("tree_", "baubles_"))], "tree_receivers")
    area("room_fill", (0.0, 1.5, 3.4), (0.0, 1.5, 0.0), 2.5, 300.0, "#ffd9a8", sy=1.5)
    spot("wall_wash", (0.0, 3.4, 6.4), (0.0, 5.0, 4.4), 220.0, cone=80, blend=0.9, hexc="#ffe6c8", radius=0.4)
    for s in (-1, 1):                                   # the top corners out of black
        spot(f"wall_wash_{s}", (s * 1.7, 3.2, 6.4), (s * 1.9, 5.0, 4.8), 160.0, cone=80, blend=0.9, hexc="#ffe6c8", radius=0.4)
    world("#0d1412", 2.0)
    # wrapped presents about 2 m back, a middle layer between the Meebit and the room
    present("present_r1", 0.95, 2.2, 0.5, 0.45, 0.42, "#1f5a3a", "#c9a04e", ribbon, turn=12)
    present("present_r2", 1.0, 2.25, 0.3, 0.3, 0.26, "#d8b25a", "#8c363d", ribbon, turn=-20).location.z = 0.42
    present("present_l1", -0.98, 2.0, 0.42, 0.42, 0.34, "#e8e0d0", "#a8823c", ribbon, turn=-8)
    present("present_l2", -1.2, 2.55, 0.36, 0.36, 0.5, "#8c363d", "#d9b25a", ribbon, turn=25)
    return {"floor_z": base_t + 0.002, "key": ((-1.1, -1.5, 2.3), 160.0, 0.7), "rim": ((1.2, -1.0, 1.9), 15.0),
            "fstop": 2.0, "fill": 35.0, "card": 1.5, "coat": 1.0,
            "inside": (bx - 0.003, by1 + 1.0)}          # the box's side walls: the Meebit must fit between them


def present(name, x, y, w, d, h, paper_hex, stripe_hex, rib_m, turn=0.0):
    """A wrapped present: foil-striped paper, a ribbon cross, a small knot."""
    m = giftpaper(name + "_paper", paper_hex, stripe_hex, width=0.12, gap=0.05)
    o = cube(name, (-w / 2, -d / 2, 0), (w / 2, d / 2, h), m, bevel=0.006)
    rw = min(w, d) * 0.14
    for p in (cube(name + "_rib_x", (-w / 2 - 0.003, -rw / 2, -0.001), (w / 2 + 0.003, rw / 2, h + 0.004), rib_m),
              cube(name + "_rib_y", (-rw / 2, -d / 2 - 0.003, -0.001), (rw / 2, d / 2 + 0.003, h + 0.004), rib_m),
              cube(name + "_knot", (-rw, -rw, h), (rw, rw, h + rw * 1.2), rib_m, bevel=0.004)):
        p.parent = o
    o.location = (x, y, 0.0)
    o.rotation_euler = (0, 0, math.radians(turn))
    return o


BUILDERS = {"capsule": capsule, "giftbox": giftbox}


# ---------- the Meebit ----------
def polished_plastic(meshes, rough=0.22, coat=1.0, coat_rough=0.03):
    """A polished plastic finish, like a collectible figure: the Meebit's own colours stay (the colour
    textures are untouched), the surface gets a low roughness and a clear coat, so the key and rim draw
    crisp highlights along every voxel edge. Real metal traits (gold chains, Robot chrome) keep their finish."""
    done = []
    for o in meshes:
        for sl in o.material_slots:
            m = sl.material
            if not m or not m.use_nodes or m.name in done:
                continue
            nt = m.node_tree
            b = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if b is None or _metal_share(b) > 0.5 or b.inputs["Transmission Weight"].default_value > 0.01:
                continue
            for link in list(b.inputs["Roughness"].links):
                nt.links.remove(link)
            b.inputs["Roughness"].default_value = rough
            b.inputs["Coat Weight"].default_value = coat
            b.inputs["Coat Roughness"].default_value = coat_rough
            b.inputs["Coat IOR"].default_value = 1.5
            done.append(m.name)
    return done


def _metal_share(bsdf):
    """How much of a part is metal: the metallic value, or the share of its metal map over 0.5."""
    links = bsdf.inputs["Metallic"].links
    if not links:
        return bsdf.inputs["Metallic"].default_value
    n = links[0].from_node
    while n.type != "TEX_IMAGE":
        ins = [i for i in n.inputs if i.links]
        if not ins:
            return 0.0
        n = ins[0].links[0].from_node
    px = np.empty(len(n.image.pixels), dtype=np.float32)
    n.image.pixels.foreach_get(px)
    return float((px[2::4] > 0.5).mean())          # glTF keeps metalness in the blue channel


def world_verts(meshes):
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in meshes:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        pts.extend(ev.matrix_world @ v.co for v in me.vertices)
        ev.to_mesh_clear()
    return pts


# ---------- camera and lights ----------
def camera(floor_z, height):
    """A level camera at the Meebit's eye level, framed with lens shift so upright lines stay upright."""
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("wallpaper_camera")
    cd.sensor_fit = "VERTICAL"
    cd.sensor_height = 24.0
    f = 0.5 / math.tan(math.radians(VFOV) / 2)
    cd.lens = f * cd.sensor_height
    cd.clip_start = 0.05
    cd.clip_end = 1000.0
    D = f * height / ((1 - TOP) - FEET)
    cz = floor_z + EYE_LEVEL * height
    cd.shift_y = -(FEET - 0.5 - f * (floor_z - cz) / D)
    cam = obj("wallpaper_camera", cd, loc=(0.0, -D, cz))
    cam.rotation_euler = (math.radians(90), 0, 0)
    sc.camera = cam
    return cam


def frame(cam, meshes):
    """Frame on the Meebit's projected outline, not its tallest point: a hat brim or headphones project
    higher or lower than the top of the geometry. Distance sets the size, lens shift the height."""
    sc = bpy.context.scene
    pts = world_verts(meshes)[::3]
    for _ in range(5):
        bpy.context.view_layer.update()
        vs = [world_to_camera_view(sc, cam, p).y for p in pts]
        cam.location.y *= (max(vs) - min(vs)) / ((1 - TOP) - FEET)
        bpy.context.view_layer.update()
        vs = [world_to_camera_view(sc, cam, p).y for p in pts]
        cam.data.shift_y += min(vs) - FEET
    bpy.context.view_layer.update()
    return -cam.location.y


def light_meebit(info, cam, D, coll, coat):
    """Key and rim softboxes that light the Meebit alone and draw its plastic highlights, a soft white card
    behind the scene for the clear coat to mirror, and a low fill under the chin."""
    fz = info["floor_z"]
    kl, ke, ks = info["key"]
    key = area("key", kl, (0, 0, fz + 1.2), ks, ke * 0.5, "#fffaf5")
    rl, re = info["rim"]
    rim = area("rim", rl, (0, 0, fz + 1.3), 0.6, re, "#f4f4ff")
    key.visible_glossy = rim.visible_glossy = True
    if info.get("key_receivers"):                       # the key lights the Meebit and these only
        kc = bpy.data.collections.new("key_receivers")
        for o in list(coll.all_objects) + [bpy.data.objects[n] for n in info["key_receivers"]]:
            kc.objects.link(o)
        key.light_linking.receiver_collection = kc
        for co in kc.collection_objects:
            co.light_linking.link_state = "INCLUDE"
    rim.light_linking.receiver_collection = coll        # the rim is for its edges only
    for co in coll.collection_objects:
        co.light_linking.link_state = "INCLUDE"
    if info.get("card"):                                # seen only in the Meebit's own reflections
        card = area("card", (0.0, 4.2, 0.05), (0, 0, fz + 1.35), 2.0, info["card"], "#f2f2f2", sy=1.0)
        card.visible_glossy, card.visible_diffuse, card.visible_transmission = True, False, True
        card.light_linking.receiver_collection = coll
    if info.get("fill"):
        area("fill_low", (0.3, -D + 0.4, fz + 0.5), (0, 0, fz + 1.3), 1.2, info["fill"], "#ffffff")
    cam.data.dof.use_dof = True                         # the Meebit sharp, the room's lights soft
    cam.data.dof.focus_distance = D
    cam.data.dof.aperture_fstop = info["fstop"]


# ---------- render ----------
def use_gpu(scene):
    """Factory settings render on the CPU. Use a GPU when this machine has one Cycles can use."""
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("METAL", "OPTIX", "CUDA", "HIP", "ONEAPI"):
        try:
            prefs.compute_device_type = kind
        except TypeError:
            continue
        prefs.get_devices()
        if any(d.type == kind for d in prefs.devices):
            for d in prefs.devices:
                d.use = d.type == kind
            scene.cycles.device = "GPU"
            return kind
    prefs.compute_device_type = "NONE"
    return "CPU"


def _settings(scene, samples, scale):
    r = scene.render
    r.engine = "CYCLES"
    r.resolution_x, r.resolution_y, r.resolution_percentage = W, H, int(round(scale * 100))
    r.filter_size = 1.2
    r.film_transparent = False
    r.dither_intensity = 1.0                            # the 8-bit phone file is dithered: no banding in the sky
    cy = scene.cycles
    for k, v in dict(samples=samples, use_adaptive_sampling=True, adaptive_threshold=0.02, use_denoising=True,
                     denoiser="OPENIMAGEDENOISE", max_bounces=8, diffuse_bounces=3, glossy_bounces=4,
                     transmission_bounces=8, transparent_max_bounces=12, caustics_reflective=False,
                     caustics_refractive=False, sample_clamp_indirect=8.0, use_light_tree=True).items():
        try:
            setattr(cy, k, v)
        except (AttributeError, TypeError):
            pass
    scene.view_settings.view_transform = "AgX"
    for look in ("AgX - Medium High Contrast", "Medium High Contrast"):
        try:
            scene.view_settings.look = look
            break
        except TypeError:
            continue
    scene.view_settings.exposure = 0.0


def _save(scene, path, depth, mode="RGB"):
    s = scene.render.image_settings
    s.file_format, s.color_depth, s.color_mode = "PNG", depth, mode
    bpy.data.images["Render Result"].save_render(filepath=path, scene=scene)


def _load(path):
    """An 8-bit PNG as stored values (sRGB for colour, 0-1 for the mask), top row first."""
    img = bpy.data.images.load(path)
    img.colorspace_settings.name = "Non-Color"
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[::-1]


def build(token, scene_name="capsule", samples=64, scale=2.0):
    """Clear the file and build the wallpaper scene around a Meebit, ready to render. Returns a dict with
    the rig, its meshes and the scene's settings."""
    if scene_name not in BUILDERS:
        raise core.MeebitError(f"Unknown scene {scene_name}; pick one of {', '.join(BUILDERS)}")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    _settings(scene, samples, scale)
    use_gpu(scene)
    info = BUILDERS[scene_name]()
    fz = info["floor_z"]
    rig = core.load(token, "ARMS_DOWN", (0.0, 0.0, fz))
    for o in bpy.data.objects:                          # the importer's bone-display sphere stays out of the render
        if o.type == "MESH" and o.parent is None and o not in core.meshes_of(rig) and o.name.startswith("Icosphere"):
            o.hide_render = True
    meshes = core.meshes_of(rig)
    plastic = polished_plastic(meshes, coat=info["coat"])
    pts = world_verts(meshes)
    height = max(p.z for p in pts) - min(p.z for p in pts)
    cam = camera(fz, height)
    D = frame(cam, meshes)
    coll = rig.users_collection[0]
    light_meebit(info, cam, D, coll, info["coat"])
    return {"rig": rig, "meshes": meshes, "info": info, "camera": cam, "distance": D, "plastic": plastic,
            "height": height, "scene": scene_name, "token": token}


def make(token, scene_name="capsule", out_dir="renders", samples=64, scale=2.0):
    """Build, render and check one wallpaper. Writes, in out_dir:
      <token>_<scene>_iphone.png   the phone file: 8-bit sRGB PNG, 2640 x 5736 at the default scale
      <token>_<scene>_master.png   the same render as a 16-bit PNG, for grading or later edits
      <token>_<scene>_mask.png     the Meebit alone, white on black, for checking the cut-out
      <token>_<scene>_report.json  where the Meebit sits and whether it passes the checks
    Returns the report."""
    t0 = time.time()
    token = core.check_token(token)
    b = build(token, scene_name, samples, scale)
    scene = bpy.context.scene
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.join(out_dir, f"{token:05d}_{scene_name}")
    bpy.ops.render.render()
    _save(scene, stem + "_iphone.png", "8")
    _save(scene, stem + "_master.png", "16")
    secs = time.time() - t0
    # the Meebit alone: everything else held out, a quick pass, its alpha saved as the mask
    keep = set(b["meshes"])
    held = [o for o in scene.objects if o.type in ("MESH", "CURVE") and o not in keep]
    for o in held:
        o.is_holdout = True
    scene.render.film_transparent = True
    scene.cycles.samples, scene.cycles.use_denoising = 8, False
    bpy.ops.render.render()
    raw = stem + "_alpha.png"
    _save(scene, raw, "8", "RGBA")
    for o in held:                                      # back as it was, so a saved .blend renders the wallpaper
        o.is_holdout = False
    scene.render.film_transparent = False
    scene.cycles.samples, scene.cycles.use_denoising = samples, True
    scene.render.image_settings.color_mode = "RGB"
    alpha = _load(raw)[..., 3]
    os.remove(raw)
    mask = bpy.data.images.new("mask", alpha.shape[1], alpha.shape[0], alpha=False)
    flat = alpha[::-1]
    mask.pixels.foreach_set(np.dstack([flat, flat, flat, np.ones_like(flat)]).astype(np.float32).ravel())
    mask.filepath_raw = stem + "_mask.png"
    mask.file_format = "PNG"
    mask.save()
    srgb = _load(stem + "_iphone.png")[..., :3]
    report = {"token": token, "scene": scene_name, "size": [scene.render.resolution_x * scene.render.resolution_percentage // 100,
                                                             scene.render.resolution_y * scene.render.resolution_percentage // 100],
              "render_seconds": round(secs, 1), "plastic_parts": b["plastic"]}
    report.update(checks(srgb, alpha, b))
    with open(stem + "_report.json", "w") as f:
        json.dump(report, f, indent=1)
    print("WALLPAPER", json.dumps(report), flush=True)
    return report


def _lab(srgb):
    lin = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    xyz = lin @ np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]).T
    xyz = xyz / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def checks(srgb, alpha, b):
    """The checks every wallpaper has to pass on the iPhone Lock Screen (iOS 26, iPhone 17 Pro layout)."""
    h, w = alpha.shape
    on = alpha > 0.5
    rows, cols = np.where(on.any(axis=1))[0], np.where(on.any(axis=0))[0]
    if not rows.size:
        return {"fails": ["the Meebit isn't in the frame"]}
    top, bot = rows.min() / h, rows.max() / h
    x0, x1 = cols.min() / w, cols.max() / w
    out, fails = {"top_from_top": round(top, 3), "feet_from_bottom": round(1 - bot, 3),
                  "left_right": [round(x0, 3), round(x1, 3)]}, []
    out["clock_overlap_pct"] = round(max(0.0, 0.269 - top) / 0.086 * 100, 1)
    if out["clock_overlap_pct"] > 25:
        fails.append(f"covers {out['clock_overlap_pct']}% of the clock digits; iOS may put the clock in front")
    feet_screen = 0.5 + (bot - 0.5) * 1.15
    out["feet_to_buttons_px"] = round((0.877 - feet_screen) * 2868)
    if out["feet_to_buttons_px"] < 20:
        fails.append(f"feet only {out['feet_to_buttons_px']} px above the flashlight and camera buttons")
    zl, zr = 0.5 - 0.5 / 1.15, 0.5 + 0.5 / 1.15
    out["zoom_margin_px"] = round(min(x0 - zl, zr - x1) * 1320)
    if out["zoom_margin_px"] < 30:
        fails.append(f"only {out['zoom_margin_px']} px inside the edge iOS crops to")
    out["clipped_px"] = int(((srgb > 0.996).any(axis=2) & on).sum())
    if out["clipped_px"] > 200 * (w / 1320) ** 2:
        fails.append(f"{out['clipped_px']} px on the Meebit are blown out")
    # separation: colour difference (CIE76) between pixels 4 px inside and 4 px outside the outline
    lab = _lab(srgb)
    des = []
    for dy, dx in ((0, 4), (0, -4), (4, 0), (-4, 0)):
        inside = on & ~np.roll(np.roll(on, -dy, 0), -dx, 1)
        ys, xs = np.where(inside)
        ys2, xs2 = np.clip(ys + dy, 0, h - 1), np.clip(xs + dx, 0, w - 1)
        des.append(np.linalg.norm(lab[ys, xs] - lab[ys2, xs2], axis=1))
    des = np.concatenate(des)
    out["edge_contrast_median"] = round(float(np.median(des)), 1)
    out["edge_weak_pct"] = round(float((des < 15).mean() * 100), 1)
    if out["edge_weak_pct"] > 35:
        fails.append(f"{out['edge_weak_pct']}% of the outline barely stands out from the background; "
                     "the cut-out may come out ragged")
    inside = b["info"].get("inside")
    if inside:                                          # the gift box: the Meebit has to fit inside the walls
        pts = world_verts(b["meshes"])
        out["box_clearance_cm"] = round(min(inside[0] - max(abs(p.x) for p in pts),
                                            inside[1] - max(p.y for p in pts)) * 100, 1)
        if out["box_clearance_cm"] < 2:
            fails.append(f"the Meebit pokes through the box ({out['box_clearance_cm']} cm)")
    out["fails"] = fails
    return out
