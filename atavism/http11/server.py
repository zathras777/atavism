from _socket import SHUT_RD, SHUT_RDWR
import logging
import socket
import threading
import select
from atavism.http11.objects import HttpRequest


class HttpServerError(Exception):
    pass


class HttpServer(object):
    """ Class that serves an HLSVideo via HTTP.
    """

    def __init__(self, host=None, port=80, handler=None):
        self.socket = None
        self.backlog = 5
        self.running = False
        self.accept_thread = None
        self.connections = []
        self.logger = logging.getLogger()
        self.host = host
        self.port = port

        if not hasattr(self, 'handler'):
            self.handler = handler

    def __del__(self):
        if self.socket is not None:
            self.socket.close()

    @property
    def is_valid(self):
        return self.socket is not None

    def make_socket(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setblocking(0)
            sock.settimeout(5)
            sock.bind((self.host, self.port))
            sock.listen(self.backlog)
            self.socket = sock
        except socket.error:
            raise HttpServerError("Unable to open a socket for {}:{}".format(self.host, self.port))

    def start(self):
        self.logger.info("HttpServer starting up")
        if self.socket is None:
            self.make_socket()
            if self.socket is None:
                raise HttpServerError("Failed to start as no socket was created.")

        self.running = True
        self.accept_thread = threading.Thread(target=self._accept_loop)
        self.accept_thread.start()

    def stop(self):
#        if self.socket is not None:
#            self.socket.shutdown(SHUT_RD)
#            self.socket.close()
#            self.socket = None

        for c in self.connections:
            c.stop()

        if self.running:
            self.running = False
            try:
                self.accept_thread.join()
            except KeyboardInterrupt as e:
                pass

        if self.socket is not None:
            self.socket.shutdown(SHUT_RD)
            self.socket.close()
            self.socket = None


    def join(self):
        self.accept_thread.join(1.0)

    def _accept_loop(self):
        self.make_socket()
        self.logger.info("Starting accept loop for {}:{}".format(self.host, self.port))
        while self.running:
            r, w, e = select.select([self.socket], [], [self.socket], 5.0)
            if len(e) > 0:
                break
            if len(r) == 0:
                continue

            try:
                ns = self.socket.accept()
                conn = HttpConnection(self, *ns)
                self.connections.append(conn)
                self.logger.info("Accepted a connection from %s.", ns)
            except socket.timeout as e:
                continue
            except (OSError, socket.error, AttributeError):
                if self.running:
                    self.logger.warning("Socket error in accept loop :-(")
                break

        self.running = False


class HttpConnection(object):
    def __init__(self, parent, sock, address):
        self.parent = parent
        self.socket = sock
        self.address = address
        self.logger = logging.getLogger()

        self.inp = b''
        self.running = True
        self.responses = []

        self.thread = threading.Thread(target=self.main_loop)
        self.thread.name = 'HttpConnection'
        self.thread.daemon = True
        self.thread.start()
        parent.connections.append(self)

    def main_loop(self):
        #todo add timeout checking...
        request = None
        self.logger.info("HttpConnection main loop started.")
        while self.running:
            ws = [self.socket] if len(self.responses) > 0 else []

            try:
                r, w, e = select.select([self.socket], ws, [self.socket], 5.0)
            except:
                break

            if len(e) > 0:
                break

            resp = self.responses[0] if len(self.responses) > 0 else None
            if len(r) > 0:
                try:
                    data = self.socket.recv(2048)
                except socket.error as e:
                    self.logger.warning("Socket error: %s", e)
                    break

                self.logger.debug("Read %d bytes from accepted socket", len(data))
                if len(data) == 0:
                    if resp is None or not resp.is_keepalive:
                        self.logger.debug("Zero byte read, keepalive not asked for, closing socket...")
                        break

                self.inp += data
                if request is None:
                    request = HttpRequest()

                read = request.read_content(self.inp)
                self.inp = self.inp[read:]

                if request.header.finished:
                    self.logger.debug(request.header)

                if request.is_complete():
                    resp = self.parent.handler(request)
                    resp.complete()
                    self.responses.append(resp)
                    request = None

            if len(w) > 0 and resp is not None:
                # only process one response each pass...
                next = resp.next_output()
                self.logger.debug("Sending %s bytes", len(next))
                try:
                    self.socket.send(next)
                except socket.error as e:
                    if self.running:
                        self.logger.warning("Unable to send via socket. Closing it. %s", e)
                    break
                if resp.send_complete():
                    if not resp.is_keepalive:
                        break
                    self.responses.pop()

        self.socket.close()
        self.running = False
        self.parent.connections.remove(self)

    def stop(self):
        self.running = False
        try:
            self.socket.shutdown(SHUT_RDWR)
        except socket.error:
            pass
