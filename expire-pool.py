#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# expires packages from all pools

import logging

from momlib import *
from util import tree


def main(options, args):
    if len(args):
        distros = args
    else:
        distros = get_pool_distros()

    # Run through our default distribution and use that for the base
    # package names.  Expire from all distributions.
    for component in DISTROS[OUR_DISTRO]["components"]:
        for source in get_sources(OUR_DISTRO, OUR_DIST, component):
            base = get_base(source)
            logging.debug("%s %s", source["Package"], source["Version"])
            logging.debug("base is %s", base)

            for distro in distros:
                expire_pool_sources(distro, source["Package"], base)


def expire_pool_sources(distro, package, base):
    """Remove sources older than the given base.

    If the base doesn't exist, then the newest source that is older is also
    kept.
    """
    pooldir = pool_directory(distro, package)
    try:
        sources = get_pool_sources(distro, package)
    except IOError:
        return

    # Find sources older than the base, record the filenames of newer ones
    bases = []
    base_found = False
    keep = []
    for source in sources:
        if base > source["Version"]:
            bases.append(source)
        else:
            if base == source["Version"]:
                base_found = True
                logging.info("Leaving %s %s %s (is base)", distro, package,
                             source["Version"])
            else:
                logging.info("Leaving %s %s %s (is newer)", distro, package,
                             source["Version"])

            keep.append(source)

    # If the base wasn't found, we want the newest source below that
    if not base_found and len(bases):
        version_sort(bases)
        source = bases.pop()
        logging.info("Leaving %s %s %s (is newest before base)",
                     distro, package, source["Version"])

        keep.append(source)

    # Identify filenames we don't want to delete
    keep_files = []
    for source in keep:
        for md5sum, size, name in files(source):
            keep_files.append(name)

    # Expire the older packages
    for source in bases:
        logging.info("Expiring %s %s %s", distro, package, source["Version"])

        for md5sum, size, name in files(source):
            if name in keep_files:
                logging.debug("Not removing %s/%s", pooldir, name)
                continue

            tree.remove("%s/%s/%s" % (ROOT, pooldir, name))
            logging.debug("Removed %s/%s", pooldir, name)

    update_pool_sources(distro, package)


if __name__ == "__main__":
    run(main, usage="%prog [DISTRO...]",
        description="expires packages from all pools")
