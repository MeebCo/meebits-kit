"""Run with blender -b --factory-startup --python-exit-code 1 --python tests/test_motion_timing.py."""
import math
from pathlib import Path
import sys
import unittest

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "blender"))
from meebits_kit import motion


def make_rig():
    armature = bpy.data.armatures.new("Timing test armature")
    rig = bpy.data.objects.new("Timing test rig", armature)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    pelvis = armature.edit_bones.new("pelvis")
    pelvis.head, pelvis.tail = (0, 0, 0), (0, 0, 1)
    bpy.ops.object.mode_set(mode="OBJECT")
    return rig


class MotionTimingTests(unittest.TestCase):
    def setUp(self):
        self.rig = make_rig()
        self.scene = bpy.context.scene
        self.scene.render.fps, self.scene.render.fps_base = 24, 1.001
        self.scene.frame_start, self.scene.frame_end = 1, 1080
        self.scene.frame_set(125, subframe=0.5)

    def tearDown(self):
        bpy.data.objects.remove(self.rig, do_unlink=True)

    def timing(self):
        return (self.scene.render.fps, self.scene.render.fps_base,
                self.scene.frame_start, self.scene.frame_end,
                self.scene.frame_current, self.scene.frame_subframe)

    def test_preserves_edit_and_authored_travel_speed(self):
        timing = self.timing()
        clip = motion.load("walk1")
        data = clip["types"]["female"]
        expected_seconds = (len(data["frames"]) - 1) / clip["fps"]
        effective_fps = timing[0] / timing[1]
        start = 48
        action = motion.apply(self.rig, "walk1", body="female", start=start,
                              set_scene_timing=False)
        self.assertEqual(self.timing(), timing)
        self.assertEqual(action.frame_range.x, start)
        self.assertAlmostEqual((action.frame_range.y - start) / effective_fps,
                               expected_seconds, places=5)
        end = start + expected_seconds * effective_fps
        self.scene.frame_set(math.floor(end), subframe=end % 1)
        self.assertAlmostEqual(self.rig.location.y, -data["speed"] * expected_seconds,
                               places=5)

    def test_default_still_sets_preview_timing(self):
        clip = motion.load("greet1")
        count = len(clip["types"]["female"]["frames"])
        motion.apply(self.rig, "greet1", body="female", start=10)
        self.assertEqual(self.timing(), (clip["fps"], 1.0, 10, 10 + count - 1, 10, 0.0))


suite = unittest.defaultTestLoader.loadTestsFromTestCase(MotionTimingTests)
if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
    raise RuntimeError("Motion timing tests failed")
