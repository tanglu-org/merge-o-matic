<%
from momlib import *
from cgi import escape

add_comment(req.form["package"], req.form["comment"])
util.redirect(req, req.form["component"]+".html")
%>
