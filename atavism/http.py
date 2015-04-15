import random
import socket
from atavism.http11.content import FileContent
from atavism.http11.objects import HttpResponse
from atavism.http11.server import HttpServer

from atavism import __version__


class HLSServerError(Exception):
    pass


class HLSServer(HttpServer):
    """ Class that serves an HLSVideo via HTTP.
    """

    def __init__(self, video=None):
        HttpServer.__init__(self)
        self.video = video
        self.find_interface()
        if self.find_interface():
            self.start()

    def make_socket(self):
        failed = []
        while len(failed) < 5:
            port = random.randint(8100, 20000)
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.setblocking(0)
                sock.settimeout(5)
                sock.bind((self.host, port))
                sock.listen(self.backlog)
                self.socket = sock
                self.port = port
                return
            except socket.error:
                pass
        raise HLSServerError("Unable to fid a suitable open port. Tried {}".format(",".join(failed)))

    def url(self):
        return "http://{}:{}{}".format(self.host, self.port, self.video.url())

    def find_interface(self):
        """ Find the local interface(s) that we will send via.
        :return: The interface to be used.
        """
        try:
            x = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            x.connect(('1.2.3.4', 56))
            interface = x.getsockname()[0]
            x.close()
            self.host = interface
            return True
        except socket.error as e:
            raise HLSServerError("Unable to find local interface.")

    def join(self):
        self.accept_thread.join(1.0)

    def handler(self, request):
        """ Create an HttpResponseObject from the request received. The server will call complete().
        :param request: The HttpRequest object to process.
        :return: The HttpResponse object.
        """
        resp = request.make_response()
        resp.add_headers({'Accept-Ranges': 'bytes',
                          'Server': 'atavism/{}'.format(__version__)})

        if request.method not in ('GET', 'HEAD'):
            resp.set_code(405)
            return resp

        rfn = self.video.find_file(request.path)
        if rfn is None:
            resp.set_code(404)
            resp.add_content("{} does not exist on this server.".format(request.path))
            return resp

        resp.set_content(FileContent(rfn))
        return resp
