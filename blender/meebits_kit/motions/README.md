# Motions

23 motions made by Bailey for MeebCo: five idles, five walks, three runs, three chats, four greetings and
three presenting gestures. Each one comes in three versions, one per Meebit skeleton:

| Skeleton | Meebits | Shoulder to wrist |
|---|---|---|
| `male` | male Humans, Pigs, Elephants, Robots, Skeletons, Dissected | 0.37 m |
| `female` | female Humans | 0.336 m |
| `visitor` | Visitors | 0.652 m |

The kit picks the version from the Meebit's arm length, so you never choose it by hand.

## The file format

One JSON file per motion, written by [`tools/export_motions.py`](../../../tools/export_motions.py). It is
plain data, so you can play these in any engine.

```text
{
  "name": "walk1", "fps": 30, "category": "walk",
  "loop": true,            false for greet and present, which play once
  "travel": true,          walks and runs; they are baked in place
  "by": "Bailey, MeebCo",
  "types": {
    "male": {
      "speed": 0.807,      metres a second over the ground, for moving a travel motion along
      "frames": [ { "pelvis": [w, x, y, z], "spine_01": [w, x, y, z], ..., "pelvis_offset": [x, y, z] }, ... ]
    },
    "female": {...}, "visitor": {...}
  }
}
```

- 25 bones per frame, with the Unreal mannequin's names (`pelvis`, `spine_01` to `spine_05`, `neck_01`,
  `neck_02`, `head`, `clavicle_l`, `upperarm_l`, `lowerarm_l`, `hand_l`, `thigh_l`, `calf_l`, `foot_l`,
  `ball_l` and the `_r` side). Bones not listed (fingers, twist bones) follow their parents.
- Each rotation is a quaternion `[w, x, y, z]`: how far that bone has turned from the T-pose, measured in
  the Meebit's space, not the bone's. Z is up, the Meebit faces -Y and its left side is +X (Blender's
  axes). To pose a bone, multiply its T-pose orientation in the rig's space by this rotation, then work
  out the bone's local rotation from its parent's. `motion.py` shows how.
- `pelvis_offset` is how far the pelvis has moved from its T-pose place, in metres, on the same axes.
- The T-pose is the one the MeebCo CDN models ship in.
