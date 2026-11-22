---
name: meebit-wallpaper
description: Make an iPhone spatial Lock Screen wallpaper of any Meebit with the Meebits Kit and Blender, from a ready-made scene (a space capsule over Earth, or a Christmas gift box) or a scene of the user's own. Use when someone asks for a Meebit wallpaper, a Lock Screen, a spatial or 3D iPhone wallpaper, or wants to put their Meebit on their phone.
---

# Meebit spatial wallpaper

iOS 26 can turn a Lock Screen photo into a spatial scene. It finds the subject, cuts it out, slides the big
clock between the subject and the background, and shifts the layers as the phone tilts. iOS works out the
depth by itself from a flat image, so the picture has to separate cleanly on its own. This skill makes that
picture of any Meebit, using what MeebCo learned making its own.

## What you need

- **Blender** 4.2 or newer (tested on 5.2). It renders on the GPU when there is one (Metal, OptiX, CUDA, HIP,
  oneAPI) and on the CPU otherwise. The CPU works; it's just slow at full size.
- **The Meebits Kit.** If you aren't already inside a clone of it, clone it:
  `git clone https://github.com/MeebCo/meebits-kit.git`
- **Internet** the first time: the kit downloads the Meebit from the MeebCo CDN (about 375 KB) and, for the
  capsule, NASA's Earth maps (about 75 MB, once; they're cached and scaled down to working size).
- The **token number** of the Meebit (1 to 20000). Ask for it if the user hasn't given one.

Find Blender: `blender` on the PATH, or `/Applications/Blender.app/Contents/MacOS/Blender` on a Mac, or
`C:\Program Files\Blender Foundation\Blender <version>\blender.exe` on Windows. Ask the user if you can't
find it; don't install anything without asking.

## Make one

From the kit's folder:

1. **Preview first.** It renders at phone size with few samples, so it's quick even on a CPU:
   ```bash
   blender -b --factory-startup --online-mode --python tools/wallpaper.py -- 8506 --preview
   ```
   Add `--scene giftbox` for the gift box. Show the user `renders/08506_capsule_iphone.png` and read
   `renders/08506_capsule_report.json`. If `fails` isn't empty, say what failed (see the checks below).
2. **Then the full render**, once the user likes the preview:
   ```bash
   blender -b --factory-startup --online-mode --python tools/wallpaper.py -- 8506
   ```
   That's 2640 x 5736 at 64 samples. On a recent Mac GPU it takes two or three minutes; on a CPU it can
   take much longer, so tell the user before starting it.
3. **Put it on the phone.** Send `<token>_<scene>_iphone.png` to the iPhone with AirDrop or iCloud Photos,
   not as a message attachment (messaging apps recompress it). On the phone, add a new Lock Screen wallpaper
   from Photos, pick it, turn on the spatial scene when iOS offers it, and leave the framing as it is: the
   kit already placed the Meebit for the clock and the buttons.

The other files: `_master.png` is the same render in 16-bit for any later editing; `_mask.png` is the
Meebit alone, for checking the cut-out; `--blend` also saves the scene so the user can open it in Blender.

Several tokens at once make one wallpaper each: `-- 8506 2785 14872`.

## The checks, and what they mean

The numbers come from an iPhone 17 Pro on iOS 26. Each report has these, and `fails` lists any that are off.

- **clock_overlap_pct**: how much of the clock digits the Meebit's head covers. Aim for about 15% to 20%.
  Over 25% and iOS can decide the subject is in the way and put the clock **in front of** the Meebit, which
  kills the effect. iOS shows the wallpaper zoomed 1.15x about its centre, which puts the digits 18.3% to
  26.9% of the wallpaper from the top. The kit frames the top of the Meebit 25.4% from the top.
- **feet_to_buttons_px**: room between the feet and the flashlight and camera buttons. Keep it over 20.
- **zoom_margin_px**: room between the Meebit and the edge iOS crops to. Keep it over 30.
- **edge_weak_pct**: share of the outline that barely stands out from what's behind it. Over 35% and iOS's
  cut-out can come out ragged. Fix it with a background that differs from the Meebit's edges in brightness
  or colour.
- **clipped_px**: pixels blown out to white on the Meebit.
- **box_clearance_cm** (gift box only): the Meebit has to fit inside the box walls.

## What we learned (keep these when changing anything)

- **The phone file is the 2x render.** iOS keeps the background sharp but renders the cut-out subject much
  softer. At 1320 x 2868 a Meebit looked blurry on the phone; at 2640 x 5736 it looked sharp. Don't
  downscale the phone file.
- **The clock needs a calm, contrasting area behind it.** Black space, a dark wall or a window. A white clock
  over a white wall disappears. The capsule keeps space behind the clock; the gift box puts a dark panel there.
- **Depth makes the effect.** iOS separates layers where it sees a depth jump. Give the background real depth:
  receding walls, a planet with clouds over it, a lit window in a far wall. A flat backdrop right behind the
  Meebit gives iOS nothing to slide.
- **Eye level, straight on.** The camera sits at the Meebit's eyes and stays level, with lens shift for the
  framing, so upright lines stay upright. A Meebit looks great because of the light and the setting, not
  because you look up its nose.
- **Keep the Meebit's own colours.** The kit gives the Meebit a polished plastic finish (low roughness and a
  clear coat) but never touches its colour textures. If a colour looks off, change the light, not the skin.
  A bright white room bounces a lot of light onto a Meebit; that's why the capsule uses less clear coat.
- **A tweak for one Meebit stays with that Meebit.** A light placed for one face (a reflection card for a
  cap, say) can draw a hard pale band on another. When you adjust a scene for one Meebit, check it on the
  next one instead of carrying it over.
- **Dark shoes, light floor; light shoes, dark floor.** The capsule has a dark walkway so white shoes stand
  out, and the feet need to read as standing on it.
- **Bright saturated colours wash out.** AgX (the view transform the kit uses) softens very bright, fully
  saturated colours, so a gold buckle or a neon print can come out pale. That's AgX, not the model.
- **Robots and chrome mirror the room.** Chrome needs something bright to reflect. In a dark scene, add a
  large white light that only the chrome sees.

## Your own scene

To make a scene of your own, start from a ready-made one with `--blend`, open the `.blend` in Blender,
change the set, and render from the camera the kit placed. Or add a builder to `SCENES` and `BUILDERS` in
`blender/meebits_kit/wallpaper.py`: a function that builds the set around a Meebit standing at the origin
facing -Y, and returns its floor height, key and rim lights, and f-stop (see `capsule()` and `giftbox()`).
Keep the framing constants (`TOP`, `FEET`) and the checks as they are; they're what make it work on the
phone. Then run the preview and read the report.

## Rights

The Meebit models stay under the [Meebits NFT License Terms](https://meebits.com/legal/license); use your
Meebits as those terms allow. The Earth maps are NASA's (Visible Earth / Earth Observatory); credit NASA if
you share a wallpaper that shows the Earth. The kit's code is MIT.
