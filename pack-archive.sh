#!/bin/sh

set -e
umask 002

cd /srv/patches.tanglu.org

find changes -name "*.changes" -mtime +182 -print0 | xargs -0r bzip2
find diffs -name "*.patch" -mtime +182 -print0 | xargs -0r bzip2
find patches \( -name "*.patch" -o -name "*.slipped-patch" \) -mtime +182 -print0 | xargs -0r bzip2
