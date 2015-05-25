""" A multithreaded, keep-alive HTTP/1.1 client object that can handle multiple
    connections.
"""
import socket
import select

try:
    from urllib.parse import urlencode, quote
except ImportError:
    from urllib import urlencode, quote

from atavism import __version__
from atavism.http11.objects import HttpRequest, HttpResponse
from atavism.http11.cookies import CookieJar


class HttpClientError(Exception):
    pass


class HttpClient(object):
    """ Http Client class. Implements an HTTP 1.1 client which uses keepalive by default.
        Requests can always be made, but may block if another request is being processed.
    """
    TIMEOUT = 5.0

    def __init__(self, host, port=80):
        self.host = host
        self.port = port
        self.socket = None

        self.cookies = CookieJar()
        self.user_agent = 'atavism/{}'.format(__version__)

        self.timeout = self.TIMEOUT
        self._buffer = b''

        if isinstance(self.host, bytes):
            self.host = self.host.decode()

    def __del__(self):
        self._close_socket()

    def host_str(self):
        if self.port == 80:
            return self.host
        return "{}:{}".format(self.host, self.port)

#    def add_cookie(self, key, value, path='/'):
#        self.cookies.set_cookie(key, value, path)

    def verify(self):
        """ Verify that the client is able to establish a connection to the server.
            NB This will not start the listener thread.
        :return: True or False
        """
        self._make_socket()
        if self.socket is not None:
            return True

    def simple_request(self, uri=None, qry=None):
        """ Really, really simple GET request. This will not follow redirects and for anything but a
            200 response will return None.
        :param uri: The server URI to GET
        :param qry: Optional query string to append.
        :return: The content of the response or None.
        """
        resp = self.request(uri, qry)
        return resp.decoded_content()

    def download_file(self, uri, filename):
        resp = self.request(uri)
        if resp is None:
            return False
        if resp.code != 200:
            raise HttpClientError("Unable to download file. Error code {}".format(resp.code))
        with open(filename, 'wb') as fh:
            fh.write(resp.content)
        return True

    def request(self, uri, qry=None):
        return self._make_send_request('GET', uri, qry=qry)

    def post_data(self, uri, qry=None, data=None, ct=None):
        """ Submit a POST request with the supplied data. """
        if ct is None and data is not None and len(data) > 0:
            ct = 'application/x-www-form-urlencoded'
        hdrs = {'Content-Type': ct}
        if data is not None:
            if ct == 'text/parameters':
                data = "\r\n".join("{}: {}".format(k, data[k]) for k in data) + "\r\n"
            elif isinstance(data, dict):
                data = urlencode(data).encode()
        return self._make_send_request('POST', uri, qry=qry, data=data, hdrs=hdrs)

    def _make_url(self, path, query=None):
        if path is None or len(path) == 0:
            path = b'/'
        else:
            path = quote(path)

        if query is not None:
            if isinstance(query, dict):
                query = urlencode(query)
            if '?' in path:
                return path + query
            return path + '?' + query
        return path

    def create_request(self, method, uri='/', qry=None, hdrs=None):
        req = HttpRequest(method=method, path=self._make_url(uri, qry))
        req.add_headers(hdrs or {})
        cookies = self.cookies.get_cookies(uri)
        if cookies is not None:
            req.add_header('Cookie', cookies)
        return req

    def _make_send_request(self, method, uri='/', qry=None, data=None, hdrs=None):
        req = self.create_request(method, uri, qry=qry, hdrs=hdrs)
        if data is not None:
            req.add_content(data)
        return self.send_request(req)

    def send_request(self, request):
        self._make_socket()
        if self.socket is None:
            return None

        request.add_headers({'Host': self.host_str(),
                             'Accept-Encoding': 'identity, gzip'})
        if self.user_agent:
            request.add_header('User-Agent', self.user_agent)
        request.complete()

        response = self._process_request(request)
        if response is None:
            raise HttpClientError("No response received from remote server.")
        return response

    def _make_socket(self):
        """ Create a new connected socket.
        :raise HttpClientError:
        """
        if self.socket is None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            sock.settimeout(5)
            try:
                sock.connect((str(self.host), self.port))
                sock.settimeout(30)
                self.socket = sock
            except socket.error:
                raise HttpClientError("Attempt to connect to '{}' on port {} failed".format(self.host, self.port))
            except socket.timeout:
                raise HttpClientError("Attempt to connect to '{}' on port {} timed out".format(self.host, self.port))
            except socket.gaierror:
                raise HttpClientError("Unable to resolve host '{}'".format(self.host))

    def _close_socket(self):
        if self.socket is not None:
            self.socket.close()
            self.socket = None
        self._buffer = b''

    def _process_request(self, request):
        """ Process a single request.
        :return: None or the HttpResponse
        """
        self._make_socket()
        # Send the entire request...
        while not request.send_complete():
            data = request.next_output()
#            print("send({})".format(data))
            if len(data) == 0:
                break

            try:
                r, w, e = select.select([], [self.socket], [self.socket], self.timeout)
            except socket.error:
                print("Select failed for socket - trying to reestablish...")
                self._close_socket()
                request.reset()
                return self._process_request(request)

            if len(e) > 0:
                raise HttpClientError("Socket reported an error.")
            elif len(w) == 0:
                raise HttpClientError("Socket timed out for write operations. Unable to send request.")
            n = self.socket.send(data)
            if n == 0:
                print("Unable to send data")
                break

        if not request.send_complete():
            raise HttpClientError("Unable to send the request.")

        # Receive the whole response...
        response = HttpResponse(self._buffer)
        while not response.is_complete():
            r, w, e = select.select([self.socket], [], [self.socket], self.timeout)
            if len(e):
                self._close_socket()
                break

            if len(r):
                data = self.socket.recv(2048)
                if len(data) == 0:
                    response.mark_complete()
                    break
                self._buffer += data
#                print(self._buffer)
                r = response.read_content(self._buffer)
                self._buffer = self._buffer[r:]

            if response.is_complete():
                break

        if response.is_complete():
            self.cookies.check_cookies(response)
            if not response.is_keepalive:
                self._close_socket()
            return response
        return None
