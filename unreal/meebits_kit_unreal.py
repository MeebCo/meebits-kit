"""Import a Meebit into the Unreal Editor by token number.

From the Output Log, with the command box set to Cmd:

    py "/path/to/meebits-kit/unreal/meebits_kit_unreal.py" 8506

Or from Python (add this folder under Project Settings > Plugins > Python > Additional Paths first):

    import meebits_kit_unreal as mk
    mk.import_meebit(8506)

You get a skeletal mesh on the Unreal mannequin skeleton, its materials and textures, and an ArmsDown
animation that holds the standard pose, all in /Game/Meebits/Meebit_08506. Unless you say otherwise, the
Meebit is also placed in the open level, standing in the ArmsDown pose. Like the mannequin's mesh, it
faces +Y; turn it with yaw (degrees).

Needs Blender (4.2 or newer) for the conversion. It is found on its own in the usual places; if it is
somewhere else, set MEEBITS_BLENDER to the Blender program.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

import unreal

HERE = os.path.dirname(os.path.abspath(__file__))
CONVERTER = os.path.join(HERE, "meebit_to_unreal.py")
FIRST, LAST = 1, 20000


def find_blender():
    env = os.environ.get("MEEBITS_BLENDER")
    if env:
        return env
    found = shutil.which("blender")
    if found:
        return found
    if sys.platform == "darwin":
        candidates = ["/Applications/Blender.app/Contents/MacOS/Blender",
                      os.path.expanduser("~/Applications/Blender.app/Contents/MacOS/Blender")]
    elif sys.platform == "win32":
        roots = [os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")]
        candidates = sorted((p for r in roots for p in glob.glob(os.path.join(r, "Blender Foundation", "Blender*",
                                                                                "blender.exe"))), reverse=True)
        candidates += glob.glob(os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Steam",
                                             "steamapps", "common", "Blender", "blender.exe"))
    else:
        candidates = ["/usr/bin/blender", "/snap/bin/blender"]
    for c in candidates:
        if os.path.isfile(c):
            return c
    raise RuntimeError("Can't find Blender. Install it from blender.org, or set MEEBITS_BLENDER to the Blender "
                       "program.")


def convert(token, out_dir):
    """Download the Meebit and write an Unreal-ready GLB with Blender. Returns its path."""
    out = os.path.join(out_dir, f"Meebit_{token:05d}.glb")
    cmd = [find_blender(), "-b", "--factory-startup", "--online-mode", "--python", CONVERTER, "--", str(token), out]
    unreal.log(f"Meebits Kit: converting Meebit {token} with Blender")
    run = subprocess.run(cmd, capture_output=True, text=True)
    if run.returncode != 0 or not os.path.isfile(out):
        tail = "\n".join((run.stdout + run.stderr).strip().splitlines()[-15:])
        raise RuntimeError(f"Blender could not convert Meebit {token}:\n{tail}")
    return out


def import_meebit(token, folder="/Game/Meebits", place=True, location=(0.0, 0.0, 0.0), yaw=0.0):
    """Import Meebit `token` into `folder`/Meebit_<token>. Returns the placed actor, or the skeletal mesh
    when place is False."""
    token = int(token)
    if not FIRST <= token <= LAST:
        raise ValueError(f"Meebits run from {FIRST} to {LAST}, so there is no Meebit {token}")
    dest = f"{folder.rstrip('/')}/Meebit_{token:05d}"

    work = tempfile.mkdtemp(prefix="meebit_")
    try:
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", convert(token, work))
        task.set_editor_property("destination_path", dest)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("save", True)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    finally:
        shutil.rmtree(work, ignore_errors=True)

    assets = [unreal.EditorAssetLibrary.load_asset(p.split(".")[0])
              for p in unreal.EditorAssetLibrary.list_assets(dest, recursive=True)]
    mesh = next((a for a in assets if isinstance(a, unreal.SkeletalMesh)), None)
    if mesh is None:
        raise RuntimeError(f"Unreal imported Meebit {token} without a skeletal mesh; see the Output Log")
    # The importer names the pose after the file. Call it ArmsDown. On a second import of the same
    # Meebit, keep the ArmsDown already there (placed Meebits use it) and drop the new copy.
    anims = [a for a in assets if isinstance(a, unreal.AnimSequence)]
    anim = next((a for a in anims if a.get_name() == "ArmsDown"), None)
    fresh = [a for a in anims if a is not anim]
    if anim is None and fresh:
        unreal.EditorAssetLibrary.rename_asset(fresh.pop(0).get_path_name().split(".")[0], f"{dest}/ArmsDown")
        anim = unreal.EditorAssetLibrary.load_asset(f"{dest}/ArmsDown")
    for extra in fresh:
        unreal.EditorAssetLibrary.delete_asset(extra.get_path_name().split(".")[0])
    unreal.log(f"Meebits Kit: imported Meebit {token} to {dest}")
    if not place:
        return mesh

    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor = actors.spawn_actor_from_object(mesh, unreal.Vector(*location), unreal.Rotator(0.0, 0.0, yaw))
    if actor is None:
        raise RuntimeError(f"Imported Meebit {token} to {dest}, but could not place it: open a level first")
    actor.set_actor_label(f"Meebit {token:05d}")
    if anim is not None:
        comp = actor.get_editor_property("skeletal_mesh_component")
        comp.set_editor_property("animation_mode", unreal.AnimationMode.ANIMATION_SINGLE_NODE)
        data = comp.get_editor_property("animation_data")
        data.set_editor_property("anim_to_play", anim)
        comp.set_editor_property("animation_data", data)
    return actor


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a.strip()]
    if not args:
        unreal.log_error("Meebits Kit: give a token number, for example: py meebits_kit_unreal.py 8506")
    for i, t in enumerate(args):
        import_meebit(int(t), location=(i * 90.0, 0.0, 0.0))
