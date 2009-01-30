<%
from momlib import *
import fcntl
from cgi import escape

def add_comment(package, comment, file):
    """Add a comment to the comments file"""
    file_comments = open(file, "a")
    fcntl.lockf(file_comments, fcntl.LOCK_EX)
    the_comment = comment.replace("\n", " ")
    the_comment = escape(the_comment[:100], quote=True)
    file_comments.write("%s: %s\n" % (package, the_comment))
    file_comments.close()

add_comment(req.form["package"], req.form["comment"], ROOT+"/merges/.comments")
util.redirect(req, req.form["component"]+".html")
%>
