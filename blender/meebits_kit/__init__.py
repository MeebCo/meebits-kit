"""Meebits Kit for Blender: type a token number, get the Meebit.

The panel lives in the 3D view's sidebar (N), in the Meebits tab.
"""
import bpy
from bpy.props import EnumProperty, IntProperty, PointerProperty

from . import core, look


class MeebitsKitSettings(bpy.types.PropertyGroup):
    token: IntProperty(name="Token", description="The Meebit's token number", default=1,
                       min=core.FIRST, max=core.LAST)
    pose: EnumProperty(name="Pose", items=[(k, v.split(",")[0], v) for k, v in core.POSES.items()],
                       default="ARMS_DOWN")


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
        rigs = [o for o in context.selected_objects if o.type == "ARMATURE" and "meebit_token" in o]
        rigs += [o.parent for o in context.selected_objects
                 if o.parent and o.parent.type == "ARMATURE" and "meebit_token" in o.parent and o.parent not in rigs]
        if not rigs:
            self.report({"WARNING"}, "Select a Meebit first")
            return {"CANCELLED"}
        for rig in rigs:
            floor = core.lowest_point(rig)
            core.pose(rig, self.pose)
            rig.location.z += floor - core.lowest_point(rig)
        return {"FINISHED"}


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
        col.operator(MEEBITS_OT_house_look.bl_idname, icon="LIGHT_SUN")
        col.operator("render.render", text="Render", icon="RENDER_STILL").use_viewport = False
        if not getattr(bpy.app, "online_access", True):
            box = col.box()
            box.label(text="Blender is offline:", icon="ERROR")
            box.label(text="Preferences > System >")
            box.label(text="Allow Online Access")


classes = (MeebitsKitSettings, MEEBITS_OT_load, MEEBITS_OT_pose, MEEBITS_OT_house_look, VIEW3D_PT_meebits)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.meebits_kit = PointerProperty(type=MeebitsKitSettings)


def unregister():
    del bpy.types.Scene.meebits_kit
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
