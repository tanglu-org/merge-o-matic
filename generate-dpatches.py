#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# generate extracted debian patches for new packages

import os
import logging

from momlib import *
from util import tree


def options(parser):
    parser.add_option("-p", "--package", type="string", metavar="PACKAGE",
                      action="append",
                      help="Process only theses packages")
    parser.add_option("-c", "--component", type="string", metavar="COMPONENT",
                      action="append",
                      help="Process only these components")

def main(options, args):
    if len(args):
        distros = args
    else:
        distros = get_pool_distros()

    # For each package in the given distributions, iterate the pool in order
    # and extract patches from debian/patches
    for distro in distros:
        for dist in DISTROS[distro]["dists"]:
            for component in DISTROS[distro]["components"]:
                if options.component is not None \
                       and component not in options.component:
                    continue

                for source in get_sources(distro, dist, component):
                    if options.package is not None \
                           and source["Package"] not in options.package:
                        continue

                    sources = get_pool_sources(distro, source["Package"])
                    version_sort(sources)

                    for source in sources:
                        generate_dpatch(distro, source)

def generate_dpatch(distro, source):
    """Generate the extracted patches."""
    logging.debug("%s: %s %s", distro, source["Package"], source["Version"])

    stamp = "%s/%s/dpatch-stamp-%s" \
        % (ROOT, source["Directory"], source["Version"])

    if not os.path.isfile(stamp):
        open(stamp, "w").close()

        unpack_source(source)
        try:
            dirname = dpatch_directory(distro, source)
            extract_dpatches(dirname, source)
            logging.info("Saved dpatches: %s", tree.subdir(ROOT, dirname))
        finally:
            cleanup_source(source)

def extract_dpatches(dirname, source):
    """Extract patches from debian/patches."""
    srcdir = unpack_directory(source)
    patchdir = "%s/debian/patches" % srcdir

    if not os.path.isdir(patchdir):
        logging.debug("No debian/patches")
        return

    for patch in tree.walk(patchdir):
        if os.path.basename(patch) in ["00list", "series", "README",
                                       ".svn", "CVS", ".bzr", ".git"]:
            continue
        elif not len(patch):
            continue

        logging.debug("%s", patch)
        src_filename = "%s/%s" % (patchdir, patch)
        dest_filename = "%s/%s" % (dirname, patch)

        ensure(dest_filename)
        tree.copyfile(src_filename, dest_filename)


if __name__ == "__main__":
    run(main, options, usage="%prog [DISTRO...]",
        description="generate changes and diff files for new packages")
