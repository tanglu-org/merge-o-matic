import urlparse
import urllib
import urllib2
import re
import StringIO
import sys

class WebInterface:
    def __init__(self, baseurl):
        self.baseurl = baseurl

    def login(self, username, password):
        return Session(self, username, password)

class InvalidProduct(ValueError): pass
class InvalidComponent(ValueError): pass
class InvalidVersion(ValueError): pass
class InvalidPriority(ValueError): pass
class InvalidSeverity(ValueError): pass
class InvalidPlatform(ValueError): pass
class InvalidStatus(ValueError): pass
class InvalidOS(ValueError): pass
class InvalidKeyword(ValueError): pass
class LoginFailure(Exception): pass
class UnknownError(Exception): pass
class InternalError(Exception): pass

class Session:
    def __init__(self, instance, username, password):
        self.instance = instance
        self.username = username
        self.password = password

        # Doesn't actually try to login (yet)

    success_pattern = re.compile('<title>Bug (\d+) Submitted</title>', re.IGNORECASE)

    # Semi-magic "leave unchanged" value for forms
    dontchange = '--do_not-change--'

    def bug_id_from_alias(self, product, alias, all=False):
        """Lookup a bug id by it's alias."""

        form = {
            'product' : product,
            'field0-0-0' : "alias",
            'type0-0-0' : "equals",
            'value0-0-0' : alias
            }

        if not all:
            form['bug_status'] = [ "NEW", "ASSIGNED", "REOPENED" ]

        result = self._form_submit('buglist.cgi', form)

        id_pattern = re.compile(r'show_bug.cgi\?id=(\d+)', re.IGNORECASE)

        bug_id = None
        for line in result.readlines():
            match = id_pattern.search(line)
            if match:
                bug_id = int(match.group(1))
                break

        return bug_id

    def submit(self, product, component, version, short_desc, comment,
               priority=None, severity=None, status=None,
               assigned_to=None, cc=None, keywords=None, dependson=None,
               blocked=None,alias=None):
        """Submit a new bug"""
        
        if priority is None:
            priority = 'P2'
        if severity is None:
            severity = 'normal'
        if status is None:
            status = 'NEW'

        platform = 'Other'
        opsys = 'other'

        if comment == '':
            raise ValueError('Empty comment')

        if short_desc == '':
            raise ValueError('Empty short_desc')

        form = { 
                 'product' : product,
                 'component' : component,
                 'version' : version,
                 'short_desc' : short_desc,
                 'comment' : comment,
                 'bug_status' : status,
                 'bug_severity' : severity,
                 'priority' : priority,
                 'bug_file_loc' : 'http://',
                 'op_sys' : opsys,
                 'rep_platform' : platform,
                 'form_name' : 'enter_bug'
                 }

        if keywords is not None:
            form['keywords'] = keywords

        if alias is not None:
            form['alias'] = alias

        result = self._form_submit('post_bug.cgi', form)

        # This mess based on contrib/bugzilla-submit/bugzilla-submit by
        # Christian Reis and Eric S. Raymond
        bug_id = None
        error_text = ''
        for line in result.readlines():
            error_text += line
            text = line.lstrip()

            if text.find('A legal Product') != -1:
                raise InvalidProduct, product
            if text.find('A legal Version was not') != -1:
                raise InvalidVersion, version
            if text.find('A legal Priority') != -1:
                raise InvalidPriority, priority
            if text.find('A legal Severity') != -1:
                raise InvalidSeverity, severity
            if text.find('A legal Status') != -1:
                raise InvalidStatus, status
            if text.find('A legal Platform') != -1:
                raise InvalidPlatform, platform
            if text.find('A legal OS') != -1:
                raise InvalidOS, opsys
            if text.find('Component Needed') != -1:
                raise InvalidComponent, component
            if (text.find('Invalid Username') != -1 or
                text.find('The username or password you entered is not valid') != -1 or
                text.find('I need a legitimate login and password to continue') != -1):
                raise LoginFailure
            if bug_id == None:
                match = self.success_pattern.search(line)
                if match:
                    bug_id = int(match.group(1))

        if bug_id is None:
            sys.stderr.write(error_text)
            raise UnknownError, 'Neither error nor bug ID found in HTML response'

        return bug_id

    def add_comment(self, bug_id, comment):
        form = {
            'id_%d' % bug_id : 1,
            'comment' : comment,
            'product' : self.dontchange,
            'component' : self.dontchange,
            'version' : self.dontchange,
            'target_milestone' : self.dontchange,
            'knob' : 'none',
            'multiupdate' : 'Y',
            'form_name' : 'buglist',
            }

        result = self._form_submit('process_bug.cgi', form)
        #print result.read()

    def clear_alias(self, bug_id):
        form = {
            'id_%d' % bug_id : 1,
            'alias' : '',
            'product' : self.dontchange,
            'component' : self.dontchange,
            'version' : self.dontchange,
            'target_milestone' : self.dontchange,
            'knob' : 'none',
            'multiupdate' : 'Y',
            'form_name' : 'buglist',
            }

        result = self._form_submit('process_bug.cgi', form)

    def add_attachment(self, bug_id, attachment, mimetype='text/plain', filename=None, description=None):
        # urllib2 doesn't support file uploads as of Python 2.3
        raise Warning, 'Attachment submission to Bugzilla not implemented yet'
    
        if description is None:
            description = ''
        if filename is None:
            filename = ''

        form = {
            'action' : 'insert',
            'contenttypemethod' : 'manual',
            'contenttypeentry' : mimetype,
            'description' : description,
            'filename' : filename,
            'data' : attachment,
            }

        result = self._form_submit('attachment.cgi', form)
        print result.read()

    def mark_duplicate(self, duplicate_bug, bug, comment):
        form = {
            'id_%d' % duplicate_bug : 1,
            'knob' : 'duplicate',
            'dup_id' : bug,
            'comment' : comment,
            'product' : self.dontchange,
            'component' : self.dontchange,
            'version' : self.dontchange,
            #'target_milestone' : self.dontchange, # Doesn't work -mdz
            'target_milestone' : '---',
            'multiupdate' : 'Y',
            'form_name' : 'buglist',
            }

        result = self._form_submit('process_bug.cgi', form)
        #print result.read()

    def _form_submit(self, relative_url, valdict):
        form = valdict.copy()
        form['Bugzilla_login'] = self.username
        form['Bugzilla_password'] = self.password
        form['GoAheadAndLogIn'] = 1
        form['dontchange'] = self.dontchange

        #print `form`
        url = urlparse.urljoin(self.instance.baseurl, relative_url)
        return urllib2.urlopen(url, urllib.urlencode(form, doseq=1))

if __name__ == '__main__':
    session = WebInterface('https://bugzilla.warthogs.hbd.com/bugzilladev/').login('test@no-name-yet.com', 'w4PfEeG6')
    bugid = session.submit(product='TestProduct', component='TestComponent', version='other',
                           short_desc='Test bug from bugzilla.py:__main__',
                           comment='This really is a test')
    print "Submitted as bug %d" % bugid
    session.add_comment(bugid, 'automated test comment')
    #session.add_attachment(bugid, 'A little tiny attachment')
