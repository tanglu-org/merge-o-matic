#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Nightly Difference Analysis

import mom
from mom import *

mom.download_lists = False

def main():
    main = get_sources("ubuntu", UBUNTU_MIRROR, UBUNTU_DIST, "main")
    universe = get_sources("ubuntu", UBUNTU_MIRROR, UBUNTU_DIST, "universe")

    old_sources = []
    for name, mirror, dist in OLD_SOURCES:
        try:
            old_sources.append((name, mirror,
                                get_sources_list(name, mirror, dist, "main")))
        except IOError:
            print "   - Failed"

    todo = []
    if mom.args:
        for package, component in zip(mom.args[::2], mom.args[1::2]):
            if component == "main":
                ubuntu = main
            elif component == "universe":
                ubuntu = universe
            else:
                print "E: Package in unknown component: %s (%s)" % (package, component)
                continue

            if package not in ubuntu:
                print "E: Package not in %s: %s" % (component, package)

            todo.append((package, ubuntu[package]))
    else:
        todo.extend(main.items())
        todo.extend(universe.items())

    patches = []
    for package, ubuntu_info in todo:
        try:
            patch = assay(package, old_sources, ubuntu_info)
            if patch is not None:
                patches.append((package, patch))
        except KeyboardInterrupt:
            raise
        except SystemExit:
            raise

        except Excuse, e:
            print "W:", str(e)
            continue
        except Problem, e:
            print "E:", str(e)
            continue
        except:
            print traceback.format_exc()

    f = open("%s/PATCHES" % PATCHES_DIR, "w")
    try:
        for package, patch in patches:
            print >>f, "%s %s" % (package, patch)
    finally:
        f.close()


def assay(package, old_sources, ubuntu_info):
    """Compare the differences between a Debian and Ubuntu package."""
    print
    print " * Processing %s" % package

    # Check there's still an ubuntu diff
    ubuntu_ver = version.Version(ubuntu_info["Version"])
    if "ubuntu" not in ubuntu_info["Version"]:
        make_history(package)
        return None

    # Work out the base version
    if "ubuntu" not in ubuntu_info["Version"]:
        raise Problem, "Package has no ubuntu version component: %s (%s)" % (package, ubuntu_ver)
    find_str = ubuntu_info["Version"][:ubuntu_info["Version"].index("ubuntu")]
    if find_str.endswith("-"):
        find_str += "0"
    find_ver = version.Version(find_str)

    # Look through the old_sources and find the nearest
    (base_mirror, base_info, base_ver) = find_base(old_sources, package,
                                                   find_ver)

    # Download the sources
    download_source(UBUNTU_MIRROR, ubuntu_info)
    download_source(base_mirror, base_info)

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
    mom.args = sys.argv[1:]
    while mom.args:
        if mom.args[0] == "--help":
            print "Usage: nda OPTION... (PACKAGE SECTION)..."
            print
            print "Options:"
            print "  --help          Show this message"
            print "  --force         Always process merges"
            print "  --download      Download package lists again"
            sys.exit(0)
        elif mom.args[0] == "--download":
            mom.download_lists = True
            mom.args.pop(0)
        elif mom.args[0] == "--":
            mom.args.pop(0)
            break
        elif mom.args[0].startswith("--"):
            print "Unknown option: %s" % mom.args[0]
            sys.exit(1)
        else:
            break

    main()
