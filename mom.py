#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Merge-O-Matic


import os
import sys
import gzip
import time
import shutil
import urllib

from sets import Set

import bugzilla
from deb import controlfile, source, version
from util import compress, shell, tree


# Location of Ubuntu and Debian mirrors to use
UBUNTU_MIRROR   = "http://archive.ubuntu.com/ubuntu"
DEBIAN_MIRROR   = "http://ftp.uk.debian.org/debian"
SNAPSHOT_MIRROR = "http://snapshot.debian.net/archive"

# Ubuntu distribution to merge into
UBUNTU_DIST = "breezy"

# Where do we get our orders?
JOBLIST_URL = "http://jackass/lorraine/needs-merged.txt"

# Places to put things
CACHE_DIR   = "cache"
FILES_DIR   = "files"
SOURCES_DIR = "sources"
WORK_DIR    = "work"
FINAL_DIR   = "public_html/ongoing-merge"
PATCHES_DIR = "public_html/patches"

# URL of FINAL_DIR
FINAL_URL = "http://people.ubuntu.com/~scott/ongoing-merge"

# Where we file bugs
BUGZILLA_URL      = "https://bugzilla.ubuntu.com/"
BUGZILLA_USERNAME = "scott-bugs@canonical.com"
BUGZILLA_PASSWORD = "mka773624"
BUGZILLA_PRODUCT  = "Ubuntu"


class Problem(Exception): pass
class Excuse(Exception): pass


def main():
    unstable = get_sources(DEBIAN_MIRROR, "unstable", "main")
    main = get_sources(UBUNTU_MIRROR, UBUNTU_DIST, "main")
    universe = get_sources(UBUNTU_MIRROR, UBUNTU_DIST, "universe")

    jobs = get_joblist()
    for package, component in jobs:
        try:
            print
            print " * Processing %s" % package

            (debian_info, debian_ver, ubuntu_info, ubuntu_ver,
             base_info, base_ver) = find_info(package, component, unstable, main, universe)

            (debian_dsc, debian_patch, ubuntu_dsc, ubuntu_patch,
             base_dsc, final_dir) = prepare(package, debian_info, debian_ver,
                                            ubuntu_info, ubuntu_ver,
                                            base_info, base_ver)

            (merged_ver, merged_dsc, merged_patch, winning_side) \
                         = merge(package, debian_ver, debian_dsc, debian_patch,
                                 ubuntu_ver, ubuntu_dsc, ubuntu_patch,
                                 base_ver, base_dsc, final_dir)

            write_report(package, debian_ver, ubuntu_ver, base_ver, merged_ver,
                         final_dir, winning_side)

            try:
                if len(sys.argv) <= 1:
                    file_bug(package, component)
            except Exception, e:
                print >>sys.stderr, "W: Unable to file bug: %s" % str(e)

        except Excuse, e:
            print >>sys.stderr, "W:", str(e)
            continue
        except Problem, e:
            print >>sys.stderr, "E:", str(e)
            continue


def find_info(package, component, unstable, main, universe):
    """Find the information for a particular package."""

    # Find the package information in unstable
    if package not in unstable:
        raise Problem, "Package not in unstable: %s" % package

    debian_info = unstable[package]
    debian_ver = version.Version(debian_info["Version"])
    print "   - unstable: %s" % debian_ver

    # Find the package information in ubuntu main/universe
    if component == "main":
        ubuntu = main
    elif component == "universe":
        ubuntu = universe
    else:
        raise Problem, "Package in unknown component: %s (%s)" % (package, component)

    if package not in ubuntu:
        raise Problem, "Package not in %s: %s" % (component, package)

    ubuntu_info = ubuntu[package]
    ubuntu_ver = version.Version(ubuntu_info["Version"])
    print "   - %s: %s" % (component, ubuntu_ver)

    # Figure out and find the base version using snapshot.debian.net
    if "ubuntu" not in ubuntu_info["Version"]:
        raise Problem, "Package has no ubuntu version component: %s (%s)" % (package, ubuntu_ver)

    find_ver = version.Version(ubuntu_info["Version"][:ubuntu_info["Version"].index("ubuntu")])
    (base_info, base_ver) = find_snapshot(package, find_ver)
    if base_info is None:
        raise Problem, "Package base version not found: %s (%s)" % (package, find_ver)

    # Sanity check base version
    print "   - base: %s" % base_ver
    if base_ver == debian_ver:
        raise Excuse, "Debian hasn't moved from base, skipping: %s (%s = %s)" % (package, base_ver, debian_ver)
    elif base_ver > debian_ver:
        raise Excuse, "Debian behind our base version, skipping: %s (%s > %s)" % (package, base_ver, debian_ver)
    elif base_ver > ubuntu_ver:
        raise Excuse, "Ubuntu behind the base version (huh?), skipping: %s (%s > %s)" % (package, base_ver, ubuntu_ver)
    elif ubuntu_ver > debian_ver:
        raise Excuse, "Ubuntu ran ahead of Debian, skipping: %s (%s > %s)" % (package, ubuntu_ver, debian_ver)

    return (debian_info, debian_ver, ubuntu_info, ubuntu_ver,
            base_info, base_ver)


def get_sources(mirror, dist, component):
    """Return a dictionary of source package to information."""
    filename = update_sources(mirror, dist, component)
    gzfile = gzip.open(filename)
    try:
        sources = controlfile.ControlFile(fileobj=gzfile, multi_para=True)
    finally:
        gzfile.close()

    result = {}
    for para in sources.paras:
        result[para["Package"]] = para

    return result

def update_sources(mirror, dist, component):
    """Update the local Sources cache."""
    filename = "%s/%s-%s.sources.gz" % (CACHE_DIR, dist, component)
    url = "%s/dists/%s/%s/source/Sources.gz" % (mirror, dist, component)

    print " * Downloading %s" % url
    urllib.urlretrieve(url, filename)

    return filename

def find_snapshot(package, find_version):
    """Find an old version of a package on snapshot.debian.net."""
    filename = update_snapshot_sources(SNAPSHOT_MIRROR, package)
    gzfile = gzip.open(filename)
    try:
        sources = controlfile.ControlFile(fileobj=gzfile, multi_para=True)
    finally:
        gzfile.close()

    nearest_para = None
    nearest_version = None
    for para in sources.paras:
        if para["Package"] != package:
            continue

        para_version = version.Version(para["Version"])
        if para_version == find_version:
            return (para, find_version)
        elif para_version < find_version \
             and (nearest_version is None or nearest_version < para_version):
            nearest_para = para
            nearest_version = para_version
    else:
        return (nearest_para, nearest_version)

def update_snapshot_sources(mirror, package):
    """Update the local Sources cache of package snapshots."""
    filename = "%s/snapshot-%s.sources.gz" % (CACHE_DIR, package)
    url = "%s/source/Sources.gz" % pool_url(SNAPSHOT_MIRROR, package)

    print " * Downloading %s" % url
    urllib.urlretrieve(url, filename)

    return filename

def pool_url(mirror, package):
    """Return a URL into the pool."""
    if package.startswith("lib"):
        package_dir = package[:4]
    else:
        package_dir = package[:1]

    return "%s/pool/%s/%s" % (mirror, package_dir, package)


def get_joblist():
    """Return (package, component) for each job."""
    if len(sys.argv) > 1 and sys.argv[1][0] != '-':
        return zip(sys.argv[1::2], sys.argv[2::2])

    result = []
    filename = update_joblist()
    f = open(filename)
    try:
        for line in f:
            result.append(line.rstrip("\n").split(" ", 1))
    finally:
        f.close()

    return result

def update_joblist():
    """Update the local job list cache."""
    filename = "%s/needs-merged.txt" % CACHE_DIR
    url = JOBLIST_URL

    print " * Downloading %s" % url
    urllib.urlretrieve(url, filename)

    return filename


def prepare(package, debian_info, debian_ver, ubuntu_info, ubuntu_ver,
            base_info, base_ver):
    """Prepare the package for patching."""

    # Download the sources
    changed = False
    changed |= download_source(DEBIAN_MIRROR, debian_info)
    changed |= download_source(UBUNTU_MIRROR, ubuntu_info)
    changed |= download_source(SNAPSHOT_MIRROR, base_info)

    if not changed:
        raise Excuse, "Not changed since last run: %s" % package

    debian_dsc = debian_info["_dsc_file"]
    ubuntu_dsc = ubuntu_info["_dsc_file"]
    base_dsc = base_info["_dsc_file"]

    # Create the patches
    final_dir = create_final_dir(package)
    debian_patch = create_patch("debian", package, base_ver, debian_ver)
    ubuntu_patch = create_patch("ubuntu", package, base_ver, ubuntu_ver)
    create_debdiff("debian", package, base_dsc, debian_dsc)
    create_debdiff("ubuntu", package, base_dsc, ubuntu_dsc)

    return (debian_dsc, debian_patch, ubuntu_dsc, ubuntu_patch, base_dsc,
            final_dir)


def unpack_source(dsc_file):
    """Unpack package source, return False if already unpacked."""
    files_dir = os.path.dirname(dsc_file)

    s = source.SourceControl(dsc_file)
    dest = "%s/%s_%s" % (SOURCES_DIR, s.source, s.version)
    if os.path.exists(dest):
        return False

    print " * Unpacking %s_%s" % (s.source, s.version)

    tar_file = os.path.join(files_dir, s.tar.name)
    if not os.path.exists(tar_file):
        raise Problem, "Missing tar file: %s" % s.tar.name

    tmpdir = "%s/,,unpack.%s" % (SOURCES_DIR, s.tar.name)
    os.mkdir(tmpdir)
    try:
        cmd = ( "tar", "xzf", tar_file, "-C", tmpdir )
        try:
            shell.run(cmd)
        except shell.ProcessError, e:
            raise Problem, "Unable to unpack tar file: %s: %s" \
                  % (s.tar.name, str(e))

        tree.movetree(tmpdir, dest, eat_toplevel=True)
    finally:
        tree.rmtree(tmpdir)

    if s.diff is None:
        return True

    diff_file = os.path.join(files_dir, s.diff.name)
    if not os.path.exists(diff_file):
        raise Problem, "Missing diff file: %s" % s.diff.name

    try:
        diff_gunzip = compress.open(diff_file, "r")
    except (shell.ProcessError, IOError), e:
        raise Problem, "Unable to decompress diff file: %s: %s" \
              % (s.diff.name, str(e))

    try:
        cmd = ( "patch", "-stN", "-p1" )
        try:
            shell.run(cmd, stdin=diff_gunzip, stderr=sys.stderr, chdir=dest)
        except shell.ProcessError, e:
            raise Problem, "Unable to apply diff file: %s" % s.diff.name
    finally:
        diff_gunzip.close()

    return True

def download_source(mirror, info):
    """Download sources of package, return False if already downloaded."""
    files = info["Files"].strip("\n").split("\n")
    for file in files:
        (md5sum, size, name) = file.split(None, 2)
        output = "%s/%s" % (FILES_DIR, name)

        if name.endswith(".dsc"):
            info["_dsc_file"] = output
            if os.path.exists(output):
                return False

        if os.path.exists(output):
            continue

        url = "%s/%s/%s" % (mirror, info["Directory"], name)
        print " * Downloading %s" % url
        urllib.urlretrieve(url, output)

    if "_dsc_file" not in info:
        raise Problem, "Unable to download package: %s: no dsc file" % info["Package"]

    return unpack_source(info["_dsc_file"])


def create_final_dir(package):
    """Create the final resting place, or clear it out."""
    final_dir = "%s/%s" % (FINAL_DIR, package)
    if os.path.isdir(final_dir):
        entries = os.listdir(final_dir)
        previous_entry = [ _e for _e in entries if _e[-4:] == ".dsc" ]
        if not len(previous_entry):
            tree.rmtree(final_dir)
            os.mkdir(final_dir)
            return final_dir

        previous_name = previous_entry[0][:-4]
        previous = "%s/HISTORY/%s" % (FINAL_DIR, previous_name)

        if os.path.isdir(previous):
            tree.rmtree(previous)

        os.mkdir(previous)
        for entry in entries:
            os.rename(os.path.join(final_dir, entry),
                      os.path.join(previous, entry))
    else:
        os.mkdir(final_dir)

    return final_dir

def create_patch(name, package, base, diff):
    """Create patches between two unpacked sources."""
    if name is not None:
        filename = "%s/%s/%s_%s.patch" % (FINAL_DIR, package, package, name)
    else:
        filename = "%s/%s/%s_%s.patch" % (PATCHES_DIR, package, package, diff)
    base_dir = "%s_%s" % (package, base)
    diff_dir = "%s_%s" % (package, diff)

    print " * Creating %s_%s.patch (%s -> %s)" % (package, name, base, diff)

    output = open(filename, "w")
    try:
        cmd = ( "diff", "-pruN", base_dir, diff_dir )
        try:
            shell.run(cmd, stdout=output, stderr=sys.stdout, chdir=SOURCES_DIR,
                      okstatus=(0,1,2))
        except shell.ProcessError, e:
            raise Problem, "Unable to create patch file: %s_%s.patch (%s -> %s)" \
                  % (package, name, base, diff)
    finally:
        output.close()

    return filename

def create_debdiff(name, package, base, diff):
    """Create debdiff between two sets of files."""
    filename = "%s/%s/%s_%s.debdiff" % (FINAL_DIR, package, package, name)

    print " * Creating %s_%s.debdiff (%s -> %s)" % (package, name, base, diff)

    output = open(filename, "w")
    try:
        cmd = ( "debdiff", base, diff )
        try:
            shell.run(cmd, stdout=output, stderr=sys.stdout)
        except shell.ProcessError, e:
            print >>sys.stderr, "W: Unable to create debdiff file: %s_%s.debdiff (%s -> %s)" \
                  % (package, name, base, diff)
    finally:
        output.close()

    return filename


def merge(package, debian_ver, debian_dsc, debian_patch,
          ubuntu_ver, ubuntu_dsc, ubuntu_patch, base_ver, base_dsc, final_dir):
    """Perform the merge and create a new source package."""
    merged_ver = version.Version(str(debian_ver) + "ubuntu1")

    work_dir = os.path.abspath("%s/%s_%s" % (WORK_DIR, package, merged_ver))
    os.mkdir(work_dir)
    try:
        # Work out where things are
        debian_src = "%s/%s_%s" % (SOURCES_DIR, package, debian_ver)
        ubuntu_src = "%s/%s_%s" % (SOURCES_DIR, package, ubuntu_ver)
        base_src = "%s/%s_%s" % (SOURCES_DIR, package, base_ver)

        # Try the patch both ways round and see which works better
        sides = (("debian", debian_patch, debian_src, "ubuntu", ubuntu_src),
                 ("ubuntu", ubuntu_patch, ubuntu_src, "debian", debian_src))
        (winning_dropped, winning_side, winning_work_dir) = (None, None, None)

        for right_name, right_patch, right_src, left_name, left_src in sides:
            merge_work_dir = "%s/%s" % (work_dir, right_name)
            dropped = try_merge(merge_work_dir, package, right_name,
                                right_patch, right_src, left_name, left_src,
                                base_src, merged_ver)

            if winning_dropped is None or winning_dropped > dropped:
                winning_dropped = dropped
                winning_side = right_name
                winning_work_dir = merge_work_dir

                if winning_dropped == 0:
                    break

        # Create the source package
        print " * Using result of applying %s patch" % winning_side
        merged_dsc = create_source(winning_work_dir, package,
                                   merged_ver, final_dir)

        # Create the patch (need to be careful here)
        try:
            unpack_source(merged_dsc)
            merged_patch = create_patch("merged", package,
                                        debian_ver, merged_ver)
        finally:
            tree.rmtree("%s/%s_%s" % (SOURCES_DIR, package, merged_ver))

        # Create the debdiff
        create_debdiff("merged", package, debian_dsc, merged_dsc)
    finally:
        tree.rmtree(work_dir)

    return (merged_ver, merged_dsc, merged_patch, winning_side)

def try_merge(work_dir, package, right_name, right_patch, right_src,
              left_name, left_src, base_src, merged_ver):
    """Try merging a patch onto a source package."""
    merged_src = "%s/%s_%s" % (work_dir, package, merged_ver)

    # Create copy of the left-hand version
    print " * Creating copy of %s %s" % (left_name, package)
    tree.copytree(left_src, merged_src)

    # Read the right-hand patch
    hunks = read_patch(right_patch)

    # Try to apply the right-hand patch to the left-hand version
    merged_dropped = "%s/%s_%s-dropped.patch" % (work_dir, package, right_name)
    dropped = apply_patch(work_dir, hunks, right_src, left_src, base_src,
                          merged_src, merged_dropped)

    # Add a changelog entry
    add_changelog(package, merged_ver, merged_src)

    return dropped


def read_patch(patch_file):
    """Read a patch file and return the hunks found within it."""
    file_hdr = None
    file_name = None
    hunk_hdr = None
    hunk_lines = None

    hunks = []

    print " * Considering %s" % patch_file
    patch = open(patch_file)
    for line in patch:
        line = line.rstrip("\r\n")
        if line.startswith("diff "):
            file_hdr = []
            file_hdr.append(line)

        elif line.startswith("--- "):
            file_hdr.append(line)

        elif line.startswith("+++ "):
            file_hdr.append(line)
            file_name = line[4:]
            if "\t" in file_name:
                file_name = file_name[:file_name.index("\t")]

        elif line.startswith("@@ "):
            line = line[3:]
            line = line[:line.index("@@")]

            (old, new) = line.split()
            (old_start, old_len) = split_counter(old)
            (new_start, new_len) = split_counter(new)

            hunk_hdr = [ old_start, old_len, new_start, new_len ]
            hunk_lines = []

            hunks.append([ file_hdr, file_name, hunk_hdr, hunk_lines ])
        elif line[0] in "+- ":
            hunk_lines.append(line)
    patch.close()

    return hunks

def split_counter(counter):
    """Split a patch hunk line counter."""
    if "," in counter:
        (counter_start, counter_len) = counter.split(",")
        counter_start = abs(int(counter_start))
        counter_len = int(counter_len)
    else:
        counter_start = abs(int(counter))
        counter_len = None

    return (counter_start, counter_len)

def join_counter(counter_start, counter_len):
    """Rejoin a patch hunk line counter."""
    if counter_len is None:
        return "%d" % counter_start
    else:
        return "%d,%d" % (counter_start, counter_len)

def write_hunk(out, hunk_hdr, hunk_lines):
    """Write a single hunk including line counter header."""
    (old_start, old_len, new_start, new_len) = hunk_hdr
    print >>out, "@@ -%s +%s @@" % (join_counter(old_start, old_len),
                                    join_counter(new_start, new_len))
    print >>out, "\n".join(hunk_lines)


def apply_patch(work_dir, hunks, right_src, left_src, base_src, merged_src,
                merged_dropped):
    """Apply a patch decoded by read_patch to merged_src."""
    pot_files = {}
    po_files = {}

    dropped = 0
    for file_hdr, file_name, hunk_hdr, hunk_lines in list(hunks):
        if file_name.endswith("/ChangeLog"):
            mutate_changelog(hunk_hdr, hunk_lines)

        elif file_name.endswith("/debian/changelog"):
            mutate_changelog(hunk_hdr, hunk_lines)

        elif file_name.endswith(".po"):
            po_files[file_name] = 1
            continue

        elif file_name.endswith(".pot"):
            pot_files[file_name] = 1
            continue

        if not apply_hunk(work_dir, merged_src, merged_dropped,
                          file_hdr, file_name, hunk_hdr, hunk_lines):
            dropped += 1
        else:
            update_attr(file_name, right_src, left_src, base_src, merged_src)

    for pot_file in pot_files.keys():
        if not update_pot(pot_file, right_src, left_src, base_src, merged_src):
            dropped += 1
        else:
            update_attr(file_name, right_src, left_src, base_src, merged_src)

    for po_file in po_files.keys():
        if not update_po(po_file, right_src, left_src, base_src, merged_src):
            dropped += 1
        else:
            update_attr(file_name, right_src, left_src, base_src, merged_src)

    if dropped:
        print "   - %d patch hunks dropped" % dropped
    else:
        print "   - All patch hunks applied"

    return dropped

def apply_hunk(work_dir, merged_src, merged_dropped, file_hdr, file_name,
               hunk_hdr, hunk_lines):
    """Apply a single hunk of a patch."""
    file_name = file_name[file_name.index("/") + 1:]

    orig_file = os.path.join(merged_src, file_name + ".magic-orig")
    rej_file = "%s/,,magic-reject" % work_dir
    out_file = "%s/,,magic-output" % work_dir

    out = open(out_file, "w")
    try:
        cmd = ( "patch", "-stuN", "-z", ".magic-orig", "-r", rej_file, "-p1" )
        patch = shell.open(cmd, "w", stdout=out, stderr=out, chdir=merged_src)
        print >>patch, "\n".join(file_hdr)
        write_hunk(patch, hunk_hdr, hunk_lines)
    finally:
        out.close()

    patch_worked = True

    try:
        patch.close()
    except shell.ProcessError:
        out = open(out_file)
        try:
            for line in out:
                if " FAILED -- " in line:
                    patch_worked = False
                elif "No file to patch." in line:
                    patch_worked = False
        finally:
            out.close()

        if not patch_worked:
            patch_save = open(merged_dropped, "a")
            try:
                print >>patch_save, "\n".join(file_hdr)
                write_hunk(patch_save, hunk_hdr, hunk_lines)
            finally:
                patch_save.close()

    for junk in (orig_file, rej_file, out_file):
        if os.path.isdir(junk):
            tree.rmtree(junk)
        elif os.path.exists(junk):
            os.unlink(junk)

    return patch_worked

def update_attr(filename, right_src, left_src, base_src, merged_src):
    """Update file attributes."""
    filename = filename[filename.index("/") + 1:]

    right_file = "%s/%s" % (right_src, filename)
    left_file = "%s/%s" % (left_src, filename)
    base_file = "%s/%s" % (base_src, filename)
    merged_file = "%s/%s" % (merged_src, filename)

    try:
        right_stat = os.stat(right_file)
        base_stat = os.stat(base_file)
    except OSError:
        return

    for shift in range(0, 9):
        bit = 1 << shift

        # Permission bit added on right-hand
        if not base_stat.st_mode & bit and right_stat.st_mode & bit:
            change_attr(merged_file, bit, True)

        # Permission bit removed on right-hand
        if base_stat.st_mode & bit and not right_stat.st_mode & bit:
            change_attr(merged_file, bit, False)

def change_attr(filename, bit, add):
    """Change file attributes."""
    attr = os.stat(filename).st_mode & 0777
    if add:
        attr |= bit
    else:
        attr &= ~bit

    os.chmod(filename, attr)


def mutate_changelog(hunk_hdr, hunk_lines):
    """Mutate a patch to a changelog to remove context."""
    (old_start, old_len, new_start, new_len) = hunk_hdr
    if old_start > 1 or new_start > 1:
        # Can't mutate moves
        return

    end = None
    for i, line in enumerate(hunk_lines):
        if line.startswith("-"):
            # Can't mutate removals
            return
        elif line.startswith("+"):
            if end is not None:
                # Can't mutate gaps
                return
        elif line.startswith(" "):
            if end is None:
                end = i

    if end is None:
        # Already mutated
        return

    while len(hunk_lines) > end:
        hunk_lines.pop()

    hunk_hdr[0:2] = [ 0, 0 ]
    hunk_hdr[3] = end


def strip_context(hunk_hdr, hunk_lines):
    """Strip all context from a patch (not used)."""
    (old_start, old_len, new_start, new_len) = hunk_hdr
    if old_start == 0 or new_start == 0:
        return [[ hunk_hdr, hunk_lines ]]

    new_hunk = []
    new_hunks = []
    old_len = new_len = 0

    for line in hunk_lines:
        if line.startswith(" ") or \
                (line.startswith("-#") and not line.startswith("-#,")) or \
                (line.startswith("+#") and not line.startswith("+#,")):
            if len(new_hunk):
                new_hdr = [ old_start, old_len, new_start, new_len ]
                new_hunks.append([ new_hdr, new_hunk ])
                new_hunk = []

            old_start += 1 + old_len
            new_start += 1 + new_len
            old_len = new_len = 0
        else:
            new_hunk.append(line)
            if line.startswith("+"):
                new_len += 1
            elif line.startswith("-"):
                old_len += 1

    if len(new_hunk):
        new_hdr = [ old_start, old_len, new_start, new_len ]
        new_hunks.append([ new_hdr, new_hunk ])

    return new_hunks


def update_pot(pot_file, right_src, left_src, base_src, merged_src):
    """Update a .pot file using msgcat."""
    pot_file = pot_file[pot_file.index("/") + 1:]

    right_pot = "%s/%s" % (right_src, pot_file)
    left_pot = "%s/%s" % (left_src, pot_file)
    base_pot = "%s/%s" % (base_src, pot_file)
    merged_pot = "%s/%s" % (merged_src, pot_file)

    if update_oneside(pot_file, right_pot, left_pot, base_pot, merged_pot):
        return True

    print "   - Merging POT %s" % pot_file
    try:
        cmd = ( "msgcat", "--use-first", "-o", merged_pot, right_pot,
                left_pot )
        shell.run(cmd)
    except shell.ProcessError, e:
        print "     + POT merge failed: %s" % str(e)
        return False

    return True

def update_po(po_file, right_src, left_src, base_src, merged_src):
    """Update a .po file using msgcat or msgmerge."""
    po_file = po_file[po_file.index("/") + 1:]

    right_po = "%s/%s" % (right_src, po_file)
    left_po = "%s/%s" % (left_src, po_file)
    base_po = "%s/%s" % (base_src, po_file)
    merged_po = "%s/%s" % (merged_src, po_file)

    if update_oneside(po_file, right_po, left_po, base_po, merged_po):
        return True

    closest_pot = find_closest_pot(merged_po)
    if closest_pot is None:
        return update_pot(po_file, right_src, left_src, base_src, merged_src)

    print "   - Merging PO %s" % po_file
    try:
        cmd = ( "msgmerge", "-o", merged_po, "-C", left_po, right_po,
                closest_pot )
        shell.run(cmd)
    except shell.ProcessError, e:
        print "     + PO merge failed: %s" % str(e)
        return False

    return True

def find_closest_pot(po_file):
    """Find the closest .pot file to the po file given."""
    dirname = os.path.dirname(po_file)
    for entry in os.listdir(dirname):
        if entry.endswith(".pot"):
            return os.path.join(dirname, entry)
    else:
        return None

def update_oneside(filename, right_file, left_file, base_file, merged_file):
    """Update files by copying or deleting when they only exist on one side."""
    dirname = os.path.dirname(merged_file)

    # File removed in left-hand, leave it removed
    if os.path.exists(base_file) and not os.path.exists(left_file):
        print "   + Leaving %s (removed in left-hand)" % filename
        return True

    # File removed in right-hand, remove it
    if os.path.exists(base_file) and not os.path.exists(right_file):
        if os.path.exists(merged_file):
            print "   + Removing %s (removed in right-hand)" % filename
            os.unlink(merged_file)

        return True

    # File new in left-hand only
    if os.path.exists(left_file) and not os.path.exists(right_file):
        print "   + Leaving %s (added in left-hand)" % filename
        return True

    # File new in right-hand only
    if os.path.exists(right_file) and not os.path.exists(left_file):
        if not os.path.isdir(dirname):
            os.makedirs(dirname)

        print "   + Copying %s (added in right-hand)" % filename
        shutil.copy2(right_file, merged_file)
        return True

    # Removed both sides
    if not os.path.exists(right_file) and not os.path.exists(left_file):
        print "   + Leaving %s (removed in both)" % filename
        return True

    return False


def add_changelog(package, merged_ver, merged_src):
    """Add a changelog entry to the package."""
    changelog_file = "%s/debian/changelog" % merged_src
    changelog = open(changelog_file)

    new_changelog = open(changelog_file + ".new", "w")
    print >>new_changelog, "%s (%s) hoary; urgency=low" % (package, merged_ver)
    print >>new_changelog
    print >>new_changelog, "  * Resynchronise with Debian."
    print >>new_changelog
    print >>new_changelog, (" -- Scott James Remnant <scott@canonical.com>  " +
            time.strftime("%a, %d %b %Y %H:%M:%S %z"))
    print >>new_changelog
    for line in changelog:
        print >>new_changelog, line.rstrip("\r\n")
    new_changelog.close()
    changelog.close()

    os.unlink(changelog_file)
    os.rename(changelog_file + ".new", changelog_file)


def create_source(work_dir, package, version, final_dir):
    """Create the source package, placing it in results."""
    merged_dsc = "%s_%s.dsc" % (package, version.epochal())
    print " * Creating %s" % merged_dsc
    source_dir = "%s/%s-%s" % (work_dir, package, version.upstream)
    os.rename("%s/%s_%s" % (work_dir, package, version), source_dir)

    # Grab a copy of the orig tar file
    orig_file = "%s_%s.orig.tar.gz" % (package, version.upstream)
    if os.path.exists("%s/%s" % (FILES_DIR, orig_file)):
        shutil.copy2("%s/%s" % (FILES_DIR, orig_file),
                     "%s/%s" % (work_dir, orig_file))

    # Create the .dsc file
    try:
        shell.run(("dpkg-source", "-b", "%s-%s" % (package, version.upstream)),
                  chdir=work_dir, okstatus=(0,1))
    except shell.ProcessError, e:
        raise Problem, "dpkg-source failed for %s: %s" % (merged_dsc, str(e))

    # Check the dsc file fell out
    if not os.path.exists("%s/%s" % (work_dir, merged_dsc)):
        raise Problem, "dpkg-source failed to generate %s" % merged_dsc

    # Move all the files into their final resting place
    for entry in os.listdir(work_dir):
        if os.path.isdir(os.path.join(work_dir, entry)):
            continue

        print "   - Saving %s" % entry
        os.rename(os.path.join(work_dir, entry),
                  os.path.join(final_dir, entry))

    return os.path.join(final_dir, merged_dsc)


def write_report(package, debian_ver, ubuntu_ver, base_ver, merged_ver,
                 final_dir, winning_side):
    """Write a little report."""
    report_file = "%s/REPORT" % final_dir
    report = open(report_file, "w")
    try:
        print >>report, "%s -- %s" % (package, time.ctime())
        print >>report
        print >>report, "Previous Ubuntu Version: %s" % ubuntu_ver
        print >>report, "Current Debian Version:  %s" % debian_ver
        print >>report
        print >>report, "Base Debian Version:     %s" % base_ver
        print >>report, "\t(Debian version on which I think Ubuntu is based)"
        print >>report
        print >>report, "The following patches may be useful:"
        print >>report, "\t%s_ubuntu.patch  -- changes in Ubuntu (%s -> %s)" % (package, base_ver, ubuntu_ver)
        print >>report, "\t%s_debian.patch  -- changes in Debian (%s -> %s)" % (package, base_ver, debian_ver)
        print >>report
        print >>report
        print >>report, "Merged Ubuntu Version:   %s" % merged_ver
        print >>report
        print >>report, "Check the following patch:"
        print >>report, "\t%s_merged.patch  -- new changes in Ubuntu (%s -> %s)" % (package, debian_ver, merged_ver)
        print >>report

        if os.path.exists("%s/%s_%s-dropped.patch" % (final_dir, package, winning_side)):
            print >>report, "Some %s patch hunks were dropped, see:" % winning_side.upper()
            print >>report, "\t%s_%s-dropped.patch" % (package, winning_side)
            print >>report
            print >>report, "These need to be applied manually if they are relevant."
        else:
            print >>report, "The %s patch applied with no errors." % winning_side
        print >>report

        if ubuntu_ver.upstream != merged_ver.upstream:
            sa_arg = " -sa"
        else:
            sa_arg = ""
        print >>report, "Generate .changes files using:"
        print >>report, "\tdpkg-genchanges -S -v%s%s" % (ubuntu_ver, sa_arg)
    finally:
        report.close()

def file_bug(package, component):
    """File a bug, so our hard work doesn't go to waste."""
    bzweb = bugzilla.WebInterface(BUGZILLA_URL)
    bz = bzweb.login(BUGZILLA_USERNAME, BUGZILLA_PASSWORD)

    if len(package) > 14:
        alias = "merge-%s-%s" % (package[:9], package[-4:])
    else:
        alias = "merge-%s" % package
    subject = "%s: new changes from Debian require merging" % package

    comment  = "New changes from Debian require merging into Ubuntu.\n\n"
    comment += "Some, if not all, of this work has been done automatically;\n"
    comment += "however the changes should be reviewed before signing and\n"
    comment += "uploading.\n\n"
    comment += "The new source package, along with various patches to aid\n"
    comment += "your review are available at:\n\n"
    comment += "        %s/%s/\n\n" % (FINAL_URL, package)
    comment += "In particular see the REPORT file for details.\n\n"
    comment += "If this is the first time you have received one of these\n"
    comment += "bugs, or are just unsure what to do, see:\n\n"
    comment += "        %s/README\n\n" % FINAL_URL
    comment += " -- Your friendly neighbourhood Merge-O-Matic.\n"

    nag_msg  = "This is a reminder, further changes have occurred in Debian\n"
    nag_msg += "since this report was filed.  The URL above has been updated\n"
    nag_msg += "with the new source package.\n"

    print " * Filing bug"
    bug_id = bz.bug_id_from_alias(BUGZILLA_PRODUCT, alias)
    if bug_id is not None:
        print "   - Commenting on bug %d" % bug_id

        bz.add_comment(bug_id, nag_msg)
    else:
        old_bug_id = bz.bug_id_from_alias(BUGZILLA_PRODUCT, alias, all=True)
        if old_bug_id is not None:
            bz.clear_alias(old_bug_id)

        if component == "main":
            severity = "normal"
        else:
            severity = "enhancement"

        try:
            bug_id = bz.submit(BUGZILLA_PRODUCT, package, "unspecified",
                               subject, comment, severity=severity,
                               alias=alias, keywords="merge")
            print "   - Created bug %d" % bug_id
        except bugzilla.InvalidComponent:
            bug_id = bz.submit(BUGZILLA_PRODUCT, "UNKNOWN", "unspecified",
                               subject, comment, severity=severity,
                               alias=alias, keywords="merge")
            print "   - Created bug %d on UNKNOWN" % bug_id


def analyse_patch(package, version, patch_file):
    """Analyse a patch and produce useful files of differences."""
    hunks = read_patch(patch_file)

    output = {}
    for hunk in hunks:
        category = analyse_hunk(hunk)
        if category is None:
            continue
        elif category not in output:
            output[category] = []

        output[category].append(hunk)

    write_analysed_patches(package, version, output)

def analyse_hunk(hunk):
    """Analyse a single hunk of a patch and return category for it."""
    (file_hdr, file_name, hunk_hdr, hunk_lines) = hunk

    if file_name.endswith("/ChangeLog"):
        return "changelog"
    elif file_name.endswith("/debian/changelog"):
        return "changelog"
    elif "/debian/" in file_name:
        return "packaging"
    else:
        return analyse_hunk_lines(hunk_lines)

def analyse_hunk_lines(hunk_lines):
    """Analyse the lines of a single hunk and return a category."""
    categories = Set()

    added = removed = 0

    for line in hunk_lines:
        if line.startswith("-"):
            removed += 1

            if "debian" in line.lower() and "ubuntu" not in line.lower():
                categories.add("branding")
            elif line.startswith("-\"POT-Creation-Date"):
                categories.add(None)
        elif line.startswith("+"):
            added += 1

            if "ubuntu" in line.lower() and "debian" not in line.lower():
                categories.add("branding")
            elif "lsb/init-functions" in line:
                categories.add("lsb-init")
            elif "log_success_msg" in line:
                categories.add("lsb-init")
            elif "log_failure_msg" in line:
                categories.add("lsb-init")
            elif "log_warning_msg" in line:
                categories.add("lsb-init")
            elif "log_begin_msg" in line:
                categories.add("lsb-init")
            elif "log_end_msg" in line:
                categories.add("lsb-init")
            elif line.startswith("+\"POT-Creation-Date"):
                categories.add(None)

    if "branding" in categories and (not added or not removed):
        categories.remove("branding")

    if not len(categories):
        return "unknown"
    elif len(categories) > 1:
        return "mixed"
    else:
        return categories.pop()

def write_analysed_patches(package, version, output):
    """Write result of analysing patches."""
    patch_dir = "%s/%s" % (PATCHES_DIR, package)

    categories = output.keys()
    categories.sort()

    for cat in categories:
        patch_file = "%s/%s_%s_%s.patch" % (patch_dir, package, version, cat)
        write_patch(patch_file, output[cat])

def write_patch(patch_file, hunks):
    """Write patch from hunks."""
    print " * Writing %s" % patch_file

    patch = open(patch_file, "w")
    try:
        last_file_hdr = None
        for (file_hdr, file_name, hunk_hdr, hunk_lines) in hunks:
            if file_hdr != last_file_hdr:
                print >>patch, "\n".join(file_hdr)
                last_file_hdr = file_hdr

            write_hunk(patch, hunk_hdr, hunk_lines)
    finally:
        patch.close()


if __name__ == "__main__":
    main()
