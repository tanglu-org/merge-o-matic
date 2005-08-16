#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Nightly Difference Analysis

from mom import *


def main():
    main = get_sources(UBUNTU_MIRROR, UBUNTU_DIST, "main")
    universe = get_sources(UBUNTU_MIRROR, UBUNTU_DIST, "universe")

    todo = []
    todo.extend(main.items())
    todo.extend(universe.items())

    patches = []
    for package, ubuntu_info in todo:
        try:
            patch = assay(package, ubuntu_info)
            if patch is not None:
                patches.append((package, patch))
        except Excuse, e:
            print >>sys.stderr, "W:", str(e)
            continue
        except Problem, e:
            print >>sys.stderr, "E:", str(e)
            continue
        except Exception, e:
            print >>sys.stderr, "!!", str(e)
            continue

    f = open("%s/PATCHES" % PATCHES_DIR, "w")
    try:
        for package, patch in patches:
            print >>f, "%s %s" % (package, patch)
    finally:
        f.close()


def assay(package, ubuntu_info):
    """Compare the differences between a Debian and Ubuntu package."""
    print
    print " * Processing %s" % package

    # Check there's still an ubuntu diff
    ubuntu_ver = version.Version(ubuntu_info["Version"])
    if "ubuntu" not in ubuntu_info["Version"]:
        make_history(package)
        return None

    # Work out the base version
    find_ver = version.Version(ubuntu_info["Version"][:ubuntu_info["Version"].index("ubuntu")])
    (base_info, base_ver) = find_snapshot(package, find_ver)
    if base_info is None:
        raise Problem, "Package base version not found: %s (%s)" % (package, find_ver)

    # Download the sources
    download_source(UBUNTU_MIRROR, ubuntu_info)
    download_source(SNAPSHOT_MIRROR, base_info)

    patch_dir = make_shiny(package)

    ubuntu_dsc = ubuntu_info["_dsc_file"]
    base_dsc = base_info["_dsc_file"]

    # Create the patches
    patch_file = create_patch(None, package, base_ver, ubuntu_ver)
    analyse_patch(package, ubuntu_ver, patch_file)

    return patch_file[len(PATCHES_DIR) + 1:]


def make_shiny(package):
    """Add a package to (or overwrite one in) the current patch-set."""
    patch_dir = "%s/%s" % (PATCHES_DIR, package)
    if os.path.isdir(patch_dir):
        tree.rmtree(patch_dir)

    os.mkdir(patch_dir)

    return patch_dir

def make_history(package):
    """Remove a package from the current patch-set."""
    patch_dir = "%s/%s" % (PATCHES_DIR, package)
    if os.path.isdir(patch_dir):
        previous = "%s/HISTORY/%s" % (PATCHES_DIR, package)
        if os.path.isdir(previous):
            tree.rmtree(previous)

        os.mkdir(previous)
        for entry in os.listdir(patch_dir):
            os.rename(os.path.join(patch_dir, entry),
                      os.path.join(previous, entry))


if __name__ == "__main__":
    main()

