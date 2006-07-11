#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Debian packaging.

This package provides a reasonable subset of the functionality of
dpkg-dev without being written in Perl.
"""

__copyright__ = "Copyright © 2005 Canonical Ltd."
__author__    = "Scott James Remnant <scott@canonical.com>"


from deb import controlfile
from deb import source
from deb import version
