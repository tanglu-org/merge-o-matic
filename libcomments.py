import re, string
import fcntl

def get_comments(file):
    """Extract the comments from file, and return a dictionary
       containing comments corresponding to packages"""
    comment = {}
    file_comments = open(file, "r")
    fcntl.lockf(file_comments, fcntl.LOCK_SH)
    for line in file_comments.readlines():
        splitted = line.split(": ", 1)
        package = splitted[0]
        the_comment = splitted[1]
        comment[package] = string.strip(the_comment, "\n")
    file_comments.close()
    return comment

def gen_buglink_from_comment(comment):
    """Return an HTML formatted Debian/Ubuntu bug link from comment"""
    debian = re.search(".*Debian bug #([0-9]{1,6}).*", comment, re.I)
    ubuntu = re.search(".*bug #([0-9]{1,6}).*", comment, re.I)
    if(debian):
        return "<img src=\".img/debian.png\" alt=\"Debian\" /><a href=\"http://bugs.debian.org/%s\">#%s</a>" % (debian.group(1), debian.group(1))
    elif(ubuntu):
        return "<img src=\".img/ubuntu.png\" alt=\"Ubuntu\" /><a href=\"https://launchpad.net/bugs/%s\">#%s</a>" % (ubuntu.group(1), ubuntu.group(1))
    else:
        return "&nbsp;"
