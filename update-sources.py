#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# update the Sources files in a distribution's pool

import os
import logging

from momlib import *


def main(options, args):
    if len(args):
        distros = args
    else:
        distros = get_pool_distros()

    # Iterate the pool directory of the given distributions
    for distro in distros:
        for hpart in os.listdir("%s/pool/%s" % (ROOT, distro)):
            for package in os.listdir("%s/pool/%s/%s" % (ROOT, distro, hpart)):
                update_pool_sources(distro, package)


if __name__ == "__main__":
    run(main, usage="%prog [DISTRO...]",
        description="update the Sources file in a distribution's pool")
