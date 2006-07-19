#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# mail diffs and/or patches

import os
import fcntl
import logging

from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from email.Utils import formatdate, make_msgid, parseaddr
from fnmatch import fnmatch
from smtplib import SMTP

from momlib import *
from deb.controlfile import ControlFile
from deb.version import Version


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

    subscriptions = read_subscriptions()

    # For each package in the given distributions, iterate the pool in order
    # and generate a diff from the previous version and a changes file
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

                    watermark = read_watermark(distro, source)
                    sources = get_pool_sources(distro, source["Package"])
                    version_sort(sources)

                    last = None
                    for this in sources:
                        if watermark >= this["Version"]:
                            last = this
                            continue

                        try:
                            mail_diff(distro, last, this, subscriptions)
                        except MemoryError:
                            logging.error("Ran out of memory")

                        last = this

                    save_watermark(distro, source, this["Version"])

def mail_diff(distro, last, this, subscriptions):
    """Mail a diff out to the subscribers."""
    package = this["Package"]
    logging.debug("%s: %s %s", distro, package, this["Version"])

    changes_filename = changes_file(distro, this)
    if not os.path.isfile(changes_filename):
        logging.warning("Missing changes file")
        return

    # Extract the author's e-mail from the changes file
    info = ControlFile(changes_filename, multi_para=False, signed=False).para
    if "Changed-By" not in info:
        uploader = None
    else:
        uploader = parseaddr(info["Changed-By"])[-1]

    recipients = get_recipients(distro, package, uploader, subscriptions)
    if not len(recipients):
        return

    if distro == SRC_DISTRO:
        # Debian uploads always just have a diff
        subject = "Debian %s %s" % (this["Package"], this["Version"])
        intro = MIMEText("""\
This e-mail has been sent due to an upload to Debian, and contains the
difference between the new version and the previous one.""")
        payload = diff_part(distro, this)
    elif get_base(this) == this["Version"]:
        # Never e-mail ubuntu uploads without local changes
        return
    elif last is None:
        # Initial ubuntu uploads, send the patch
        subject = "Ubuntu (new) %s %s" % (this["Package"], this["Version"])
        intro = MIMEText("""\
This e-mail has been sent due to an upload to Ubuntu of a new source package
which already contains Ubuntu changes.  It contains the difference between
the Ubuntu version and the equivalent base version in Debian.""")
        payload = patch_part(distro, this)
    elif get_base(last) != get_base(this):
        # Ubuntu changed upstream version, send the patech
        subject = "Ubuntu patch %s %s" % (this["Package"], this["Version"])
        intro = MIMEText("""\
This e-mail has been sent due to an upload to Ubuntu of a new upstream
version which still contains Ubuntu changes.  It contains the difference
between the Ubuntu version and the equivalent base version in Debian, note
that this difference may include the upstream changes.""")
        payload = patch_part(distro, this)
    else:
        # Ubuntu revision, send the diff
        subject = "Ubuntu %s %s" % (this["Package"], this["Version"])
        intro = MIMEText("""\
This e-mail has been sent due to an upload to Ubuntu that contains Ubuntu
changes.  It contains the difference between the new version and the
previous version of the same source package in Ubuntu.""")
        payload = diff_part(distro, this)

    # Allow patches to be missing (no Debian version)
    if payload is None:
        return

    # Extract the changes file
    changes = MIMEText(open(changes_filename).read())
    changes.add_header("Content-Disposition", "inline",
                       filename="%s" % os.path.basename(changes_filename))

    # Build up the message
    message = MIMEMultipart()
    message.add_header("From", "Ubuntu Merge-o-Matic <mom@ubuntu.com>")
    message.add_header("To", "Ubuntu Merge-o-Matic <mom@ubuntu.com>")
    message.add_header("Date", formatdate())
    message.add_header("Subject", subject)
    message.add_header("Message-ID", make_msgid())
    message.add_header("X-Mom-Package", package)
    message.attach(intro)
    message.attach(changes)
    message.attach(payload)

    send_message(message, recipients)

def patch_part(distro, this):
    """Construct an e-mail part containing the current patch."""
    patch_filename = patch_file(distro, this, True)
    if not os.path.isfile(patch_filename):
        patch_filename = patch_file(distro, this, False)
    if not os.path.isfile(patch_filename):
        return None

    part = MIMEText(open(patch_filename).read())
    part.add_header("Content-Disposition", "attachment",
                    filename="%s" % os.path.basename(patch_filename))
    return part

def diff_part(distro, this):
    """Construct an e-mail part containing the current diff."""
    diff_filename = diff_file(distro, this)
    if not os.path.isfile(diff_filename):
        return None

    part = MIMEText(open(diff_filename).read())
    part.add_header("Content-Disposition", "attachment",
                    filename="%s" % os.path.basename(diff_filename))
    return part


def get_recipients(distro, package, uploader, subscriptions):
    """Figure out who should receive this message."""
    recipients = []

    for sub_addr, sub_distro, sub_filter in subscriptions:
        sub_addr = sub_addr.replace("%s", package)

        if sub_distro != distro:
            continue

        if sub_filter.startswith("my:"):
            sub_filter = sub_filter[3:]

            if uploader != sub_addr:
                continue

        if not fnmatch(package, sub_filter):
            continue

        recipients.append(sub_addr)

    return recipients

def send_message(message, recipients):
    """Send out a message to everyone subscribed to it."""
    smtp = SMTP("localhost")

    for addr in recipients:
        logging.debug("Sending to %s", addr)
        message.replace_header("To", addr)

        smtp.sendmail("mom@ubuntu.com", addr , message.as_string())

    smtp.quit()


def read_subscriptions():
    """Read the subscriptions file."""
    subscriptions = []

    f = open("%s/subscriptions.txt" % ROOT)
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)

        for line in f:
            if line.startswith("#"):
                continue

            (addr, distro, filter) = line.strip().split()
            subscriptions.append((addr, distro, filter))
    finally:
        f.close()

    return subscriptions

def read_watermark(distro, source):
    """Read the watermark for a given source."""
    mark_file = "%s/%s/mail-watermark" \
                % (ROOT, pool_directory(distro, source["Package"]))
    if not os.path.isfile(mark_file):
        return Version("0")

    mark = open(mark_file)
    try:
        return Version(mark.read().strip())
    finally:
        mark.close()

def save_watermark(distro, source, version):
    """Save the watermark for a given source."""
    mark_file = "%s/%s/mail-watermark" \
                % (ROOT, pool_directory(distro, source["Package"]))
    mark = open(mark_file, "w")
    try:
        print >>mark, "%s" % version
    finally:
        mark.close()


if __name__ == "__main__":
    run(main, options, usage="%prog [DISTRO...]",
        description="mail diffs and/or patches")
