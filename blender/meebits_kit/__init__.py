"""Meebits Kit for Blender: type a token number, get the Meebit.

The panel lives in the 3D view's sidebar (N), in the Meebits tab.
"""
import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, PointerProperty

from . import core, look, motion

MOTIONS = [(n, n, f"Bailey's {n.rstrip('0123456789')} motion") for n in motion.names()]


def selected_meebits(context):
    rigs = []
    for o in context.selected_objects:
        rig = o if o.type == "ARMATURE" else o.parent
        if rig and rig.type == "ARMATURE" and "meebit_token" in rig and rig not in rigs:
            rigs.append(rig)
    return rigs


class MeebitsKitSettings(bpy.types.PropertyGroup):
    token: IntProperty(name="Token", description="The Meebit's token number", default=1,
                       min=core.FIRST, max=core.LAST)
    pose: EnumProperty(name="Pose", items=[(k, v.split(",")[0], v) for k, v in core.POSES.items()],
                       default="ARMS_DOWN")
    motion: EnumProperty(name="Motion", items=MOTIONS, description="One of Bailey's motions")
    move: BoolProperty(name="Walk forward", default=True,
                       description="Walks and runs carry the Meebit forward at the pace of its feet")


class MEEBITS_OT_load(bpy.types.Operator):
    """Download a Meebit by token number and put it at the 3D cursor"""
    bl_idname = "meebits.load"
    bl_label = "Load Meebit"
    bl_options = {"REGISTER", "UNDO"}

    token: IntProperty(name="Token", default=1, min=core.FIRST, max=core.LAST)
    pose: EnumProperty(name="Pose", items=[(k, v.split(",")[0], v) for k, v in core.POSES.items()],
                       default="ARMS_DOWN")

    def invoke(self, context, event):
        s = context.scene.meebits_kit
        self.token, self.pose = s.token, s.pose
        return self.execute(context)

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        try:
            rig = core.load(self.token, self.pose, tuple(context.scene.cursor.location))
        except core.MeebitError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Loaded {rig.name}")
        return {"FINISHED"}


class MEEBITS_OT_pose(bpy.types.Operator):
    """Put the selected Meebits in the chosen pose"""
    bl_idname = "meebits.pose"
    bl_label = "Pose Meebits"
    bl_options = {"REGISTER", "UNDO"}

    pose: EnumProperty(name="Pose", items=[(k, v.split(",")[0], v) for k, v in core.POSES.items()],
                       default="ARMS_DOWN")

    def invoke(self, context, event):
        self.pose = context.scene.meebits_kit.pose
        return self.execute(context)

    def execute(self, context):
        rigs = selected_meebits(context)
        if not rigs:
            self.report({"WARNING"}, "Select a Meebit first")
            return {"CANCELLED"}
        for rig in rigs:
            motion.stop(rig)
            floor = core.lowest_point(rig)
            core.pose(rig, self.pose)
            rig.location.z += floor - core.lowest_point(rig)
        return {"FINISHED"}


class MEEBITS_OT_motion(bpy.types.Operator):
    """Play one of Bailey's motions on the selected Meebits. Press Play in the timeline to watch"""
    bl_idname = "meebits.motion"
    bl_label = "Play Motion"
    bl_options = {"REGISTER", "UNDO"}

    motion: EnumProperty(name="Motion", items=MOTIONS)
    move: BoolProperty(name="Walk forward", default=True)

    def invoke(self, context, event):
        s = context.scene.meebits_kit
        self.motion, self.move = s.motion, s.move
        return self.execute(context)

    def execute(self, context):
        rigs = selected_meebits(context)
        if not rigs:
            self.report({"WARNING"}, "Select a Meebit first")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for rig in rigs:
            motion.apply(rig, self.motion, move=self.move)
        return {"FINISHED"}


class MEEBITS_OT_stop(bpy.types.Operator):
    """Take the motion off the selected Meebits"""
    bl_idname = "meebits.stop"
    bl_label = "Stop Motion"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        rigs = selected_meebits(context)
        for rig in rigs:
            motion.stop(rig)
        return {"FINISHED"} if rigs else {"CANCELLED"}


class MEEBITS_OT_house_look(bpy.types.Operator):
    """Add the house look: AgX, a sky, a warm sun, a floor and a low camera framing every Meebit"""
    bl_idname = "meebits.house_look"
    bl_label = "House Look"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if not core.meebits_in_scene(context.scene):
            self.report({"WARNING"}, "Load a Meebit first")
            return {"CANCELLED"}
        look.apply(context.scene)
        return {"FINISHED"}


class VIEW3D_PT_meebits(bpy.types.Panel):
    bl_label = "Meebits"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Meebits"

    def draw(self, context):
        s = context.scene.meebits_kit
        col = self.layout.column()
        col.prop(s, "token")
        col.prop(s, "pose")
        col.operator(MEEBITS_OT_load.bl_idname, icon="IMPORT")
        col.operator(MEEBITS_OT_pose.bl_idname, icon="ARMATURE_DATA")
        col.separator()
        col.prop(s, "motion")
        col.prop(s, "move")
        row = col.row(align=True)
        row.operator(MEEBITS_OT_motion.bl_idname, icon="PLAY")
        row.operator(MEEBITS_OT_stop.bl_idname, icon="X", text="Stop")
        col.separator()
        col.operator(MEEBITS_OT_house_look.bl_idname, icon="LIGHT_SUN")
        col.operator("render.render", text="Render", icon="RENDER_STILL").use_viewport = False
        if not getattr(bpy.app, "online_access", True):
            box = col.box()
            box.label(text="Blender is offline:", icon="ERROR")
            box.label(text="Preferences > System >")
            box.label(text="Allow Online Access")


classes = (MeebitsKitSettings, MEEBITS_OT_load, MEEBITS_OT_pose, MEEBITS_OT_motion, MEEBITS_OT_stop,
           MEEBITS_OT_house_look, VIEW3D_PT_meebits)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.meebits_kit = PointerProperty(type=MeebitsKitSettings)


def unregister():
    del bpy.types.Scene.meebits_kit
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
