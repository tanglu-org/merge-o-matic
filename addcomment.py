<%
from momlib import *

def add_comment(package, comment, file):
    """Add a comment to the comments file"""
    file_comments = open(file, "a")
    file_comments.write("%s: %s\n" % (package, comment))
    file_comments.close()

add_comment(req.form["package"], req.form["comment"], ROOT+"/merges/.comments")
util.redirect(req, req.form["component"]+".html")
%>
