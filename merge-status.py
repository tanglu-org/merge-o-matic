#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# output merge status

import os

from momlib import *


# Order of priorities
PRIORITY = [ "unknown", "required", "important", "standard", "optional",
             "extra" ]
COLOURS =  [ "#ff8080", "#ffb580", "#ffea80", "#dfff80", "#abff80", "#80ff8b" ]

# Sections
SECTIONS = [ "outstanding", "new", "updated" ]


def options(parser):
    parser.add_option("-D", "--source-distro", type="string", metavar="DISTRO",
                      default=SRC_DISTRO,
                      help="Source distribution")
    parser.add_option("-S", "--source-suite", type="string", metavar="SUITE",
                      default=SRC_DIST,
                      help="Source suite (aka distrorelease)")

    parser.add_option("-d", "--dest-distro", type="string", metavar="DISTRO",
                      default=OUR_DISTRO,
                      help="Destination distribution")
    parser.add_option("-s", "--dest-suite", type="string", metavar="SUITE",
                      default=OUR_DIST,
                      help="Destination suite (aka distrorelease)")

    parser.add_option("-c", "--component", type="string", metavar="COMPONENT",
                      action="append",
                      help="Process only these destination components")

def main(options, args):
    src_distro = options.source_distro
    src_dist = options.source_suite

    our_distro = options.dest_distro
    our_dist = options.dest_suite

    outstanding = []
    if os.path.isfile("%s/outstanding-merges.txt" % ROOT):
        after_uvf = True

        f = open("%s/outstanding-merges.txt" % ROOT)
        try:
            for line in f:
                outstanding.append(line.strip())
        finally:
            f.close()
    else:
        after_uvf = False
        SECTIONS.remove("new")

    # For each package in the destination distribution, find out whether
    # there's an open merge, and if so add an entry to the table for it.
    for our_component in DISTROS[our_distro]["components"]:
        if options.component is not None \
               and our_component not in options.component:
            continue

        merges = []

        for source in get_sources(our_distro, our_dist, our_component):
            try:
                output_dir = result_dir(source["Package"])
                (base_version, left_version, right_version) \
                               = read_report(output_dir,
                                             our_distro, src_distro)
            except ValueError:
                continue

            try:
                priority_idx = PRIORITY.index(source["Priority"])
            except KeyError:
                priority_idx = 0

            filename = changes_file(our_distro, source)
            if os.path.isfile(filename):
                changes = ControlFile(filename,
                                      multi_para=False, signed=False).para

                user = changes["Changed-By"]
                uploaded = changes["Distribution"] == OUR_DIST
            else:
                user = None
                uploaded = False

            if uploaded:
                section = "updated"
            elif not after_uvf:
                section = "outstanding"
            elif source["Package"] in outstanding:
                section = "outstanding"
            else:
                section = "new"

            merges.append((section, priority_idx, source["Package"], user,
                           source, base_version, left_version, right_version))

        write_status_page(our_component, merges, our_distro, src_distro)

def write_status_page(component, merges, left_distro, right_distro):
    """Write out the merge status page."""
    merges.sort()

    status_file = "%s/merges/%s.html" % (ROOT, component)
    status = open(status_file + ".new", "w")
    try:
        print >>status, "<html>"
        print >>status
        print >>status, "<head>"
        print >>status, "<title>Ubuntu Merge-o-Matic: %s</title>" % component
        print >>status, "<style>"
        print >>status, "img#ubuntu {"
        print >>status, "    border: 0;"
        print >>status, "}"
        print >>status, "h1 {"
        print >>status, "    padding-top: 0.5em;"
        print >>status, "    font-family: sans-serif;"
        print >>status, "    font-size: 2.0em;"
        print >>status, "    font-weight: bold;"
        print >>status, "}"
        print >>status, "h2 {"
        print >>status, "    padding-top: 0.5em;"
        print >>status, "    font-family: sans-serif;"
        print >>status, "    font-size: 1.5em;"
        print >>status, "    font-weight: bold;"
        print >>status, "}"
        print >>status, "p, td {"
        print >>status, "    font-family: sans-serif;"
        print >>status, "    margin-bottom: 0;"
        print >>status, "}"
        print >>status, "li {"
        print >>status, "    font-family: sans-serif;"
        print >>status, "    margin-bottom: 1em;"
        print >>status, "}"
        print >>status, "tr.first td {"
        print >>status, "    border-top: 2px solid white;"
        print >>status, "}"
        print >>status, "</style>"
        print >>status, "<body>"
        print >>status, "<img src=\".img/ubuntulogo-100.png\" id=\"ubuntu\">"
        print >>status, "<h1>Ubuntu Merge-o-Matic: %s</h1>" % component

        for section in SECTIONS:
            section_merges = [ m for m in merges if m[0] == section ]
            print >>status, ("<p><a href=\"#%s\">%s %s merges</a></p>"
                             % (section, len(section_merges), section))

        print >>status, "<ul>"
        print >>status, ("<li>If you are not the previous uploader, ask the "
                         "previous uploader before doing the merge.  This "
                         "prevents two people from doing the same work.</li>")
        print >>status, ("<li>Before uploading, update the changelog to "
                         "have your name and a list of the outstanding "
                         "Ubuntu changes.</li>")
        print >>status, ("<li>Try and keep the diff small, this may involve "
                         "manually tweaking <tt>po</tt> files and the"
                         "like.</li>")
        print >>status, "</ul>"

        for section in SECTIONS:
            section_merges = [ m for m in merges if m[0] == section ]

            print >>status, ("<h2 id=\"%s\">%s Merges</h2>"
                             % (section, section.title()))

            do_table(status, section_merges, left_distro, right_distro)

        print >>status, "<h2 id=stats>Statistics</h2>"
        print >>status, ("<img src=\"%s-now.png\" title=\"Current stats\">"
                         % component)
        print >>status, ("<img src=\"%s-trend.png\" title=\"Six month trend\">"
                         % component)
        print >>status, "</body>"
        print >>status, "</html>"
    finally:
        status.close()

    os.rename(status_file + ".new", status_file)

def do_table(status, merges, left_distro, right_distro):
    """Output a table."""
    print >>status, "<table cellspacing=0>"
    print >>status, "<tr bgcolor=#d0d0d0>"
    print >>status, "<td rowspan=2><b>Package</b></td>"
    print >>status, "<td colspan=3><b>Last Uploader</b></td>"
    print >>status, "</tr>"
    print >>status, "<tr bgcolor=#d0d0d0>"
    print >>status, "<td><b>%s Version</b></td>" % left_distro.title()
    print >>status, "<td><b>%s Version</b></td>" % right_distro.title()
    print >>status, "<td><b>Base Version</b></td>"
    print >>status, "</tr>"

    for uploaded, priority, package, user, source, \
            base_version, left_version, right_version in merges:
        if user is not None:
            user = user.replace("&", "&amp;")
            user = user.replace("<", "&lt;")
            user = user.replace(">", "&gt;")
        else:
            user = "&nbsp;"

        print >>status, "<tr bgcolor=%s class=first>" % COLOURS[priority]
        print >>status, "<td><tt><a href=\"%s/%s/REPORT\">" \
              "%s</a></tt>" % (pathhash(package), package, package)
        print >>status, " <a href=\"https://launchpad.net/distros/ubuntu/" \
              "+source/%s\">(lp)</a></td>" % package
        print >>status, "<td colspan=3>%s</td>" % user
        print >>status, "</tr>"
        print >>status, "<tr bgcolor=%s>" % COLOURS[priority]
        print >>status, "<td><small>%s</small></td>" % source["Binary"]
        print >>status, "<td>%s</td>" % left_version
        print >>status, "<td>%s</td>" % right_version
        print >>status, "<td>%s</td>" % base_version
        print >>status, "</tr>"

    print >>status, "</table>"

if __name__ == "__main__":
    run(main, options, usage="%prog",
        description="output merge status")

