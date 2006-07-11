#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# update a distribution's pool

import os
import gzip
import urllib
import logging
import tempfile

from momlib import *
from util import tree


def main(options, args):
    if len(args):
        distros = args
    else:
        distros = get_pool_distros()

    # Download the current sources for the given distributions and download
    # any new contents into our pool
    for distro in distros:
        for dist in DISTROS[distro]["dists"]:
            for component in DISTROS[distro]["components"]:
                update_sources(distro, dist, component)

                sources = get_sources(distro, dist, component)
                for source in sources:
                    update_pool(distro, source)


def sources_url(distro, dist, component):
    """Return a URL for a remote Sources.gz file."""
    mirror = DISTROS[distro]["mirror"]
    return "%s/dists/%s/%s/source/Sources.gz" % (mirror, dist, component)

def update_sources(distro, dist, component):
    """Update a Sources file."""
    url = sources_url(distro, dist, component)
    filename = sources_file(distro, dist, component)

    logging.debug("Downloading %s", url)

    urlfile = urllib.URLopener()

    gzfilename = tempfile.mktemp()
    urllib.URLopener().retrieve(url, gzfilename)
    try:
        gzfile = gzip.GzipFile(gzfilename)
        try:
            ensure(filename)
            local = open(filename, "w")
            try:
                local.write(gzfile.read())
            finally:
                local.close()
        finally:
            gzfile.close()
    finally:
        os.unlink(gzfilename)

    logging.info("Saved %s", tree.subdir(ROOT, filename))
    return filename

def update_pool(distro, source):
    """Download a source package into our pool."""
    mirror = DISTROS[distro]["mirror"]
    sourcedir = source["Directory"]

    pooldir = pool_directory(distro, source["Package"])

    for md5sum, size, name in files(source):
        url = "%s/%s/%s" % (mirror, sourcedir, name)
        filename = "%s/%s/%s" % (ROOT, pooldir, name)

        if os.path.isfile(filename):
            if os.path.getsize(filename) == int(size):
                continue

        logging.debug("Downloading %s", url)
        ensure(filename)
        urllib.URLopener().retrieve(url, filename)
        logging.info("Saved %s", tree.subdir(ROOT, filename))


if __name__ == "__main__":
    run(main, usage="%prog [DISTRO...]",
        description="update a distribution's pool")
