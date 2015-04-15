""" HTTP relies on Requests and Responses. The classes contained in this module are
    able to be created in either a client or server environment. They are named for
    their content and intent.
"""
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

from atavism.http11.base import BaseHttp


class HttpRequest(BaseHttp):
    """ An HTTP Request.
    """
    def __init__(self, inp=None, method=None, path=None):
        BaseHttp.__init__(self)
        if inp is not None:
            self.read_content(inp)
        self.method = method or 'GET'
        if path is not None:
            self.path = path if not isinstance(path, bytes) else path.decode()

    def read_content(self, data):
        if data is None or len(data) == 0:
            return 0
        hdr = self.header.finished
        rv = BaseHttp.read_content(self, data)
        if hdr is False and self.header.finished:
            self.method, self.path, self.http = self.header.status_line.split(' ')
        return rv

    def complete(self):
        if len(self.ranges) > 0:
            self.add_header('Range', 'bytes={}'.format(','.join([r.header() for r in self.ranges])))
        self.header.status_line = '{} {} {}'.format(self.method.upper(), self.path, self.http)
        self._complete()

    def make_response(self):
        resp = HttpResponse()

        resp.close_connection = self.close_connection
        resp.ranges = self.ranges

        if self.method.upper() == b'HEAD':
            resp.headers_only = True

        ce = self.get('accept-encoding')
        if ce is not None and 'gzip' in ce:
            # todo - handle this properly
            resp.set_compression('gzip')
        return resp


class HttpResponse(BaseHttp):
    """ Class that represents a response from an HTTP server.
    """
    #todo - expand list
    STATUS_MSG = {
        200: 'OK',
        206: 'Partial Content',
        301: 'Moved permanently',
        401: 'Unathorised',
        402: 'Payment required',
        403: 'Forbidden',
        404: 'Not found',
        405: 'Method not allowed',
        416: 'Requested range not satisfiable'
    }

    def __init__(self, inp=None, code=None):
        BaseHttp.__init__(self)
        self.msg = 'OK'
        self.code = code or 200
        if inp is not None:
            self.read_content(inp)

    def read_content(self, data):
        if data is None or len(data) == 0:
            return 0
        hdr = self.header.finished
        rv = BaseHttp.read_content(self, data)
        if hdr is False and self.header.finished:
            self.http, self.code, self.msg = self.header.status_line.split(' ', 2)
            self.code = int(self.code)
        return rv

    def status_msg(self):
        return self.STATUS_MSG.get(self.code, "Unknown status! {}".format(self.code))

    def set_code(self, code):
        """ Set the ode to use for the response and set
        :param code: The numeric error code to respond with.
        :return: None.
        """
        self.code = code
        if code >= 400:
            self.ranges = []
        elif code == 206 and len(self.ranges) == 0:
            self.code = 200

    def complete(self):
        if len(self.ranges) > 0:
            self.check_ranges()
            if self.code == 200:
                self.code = 206

        hdrs = self._content.create_ranged_output(self.ranges)
        self.header.add_headers(hdrs)
        self.header.status_line = 'HTTP/1.1 {} {}'.format(self.code, self.status_msg())
        self._complete()

    def check_ranges(self):
        for r in self.ranges:
            st, end = r.absolutes(len(self))
            if 0 < st >= len(self) or st > end >= len(self):
                self.set_code(416)
                break
