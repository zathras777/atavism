import gzip
import json
import mimetypes
import os
import zlib

try:
    from cStringIO import StringIO as GzipIO
except ImportError:
    from io import BytesIO as GzipIO

try:
    from plistlib import loads as plist_loads
except ImportError:
    from plistlib import readPlistFromString as plist_loads


class Content(object):
    """ Class to manage content for an HTTP transaction (i.e. a Request or a Response).
        The class can accept content from a network stream via read_content() or
        directly using add_content.
        The class maintains enough information about it's contents to allow HTTP headers
        to be generated.
        As each instance can contain only one type of data, if the data is compressed or
        manipulated another instance will be created with the new data, and the 'next' field
        will point to it.
        All functions that access/manipulate data handle this case, so the actual content of
        an instance should never be accessed directly. Calling the appropriate function on the
        root object in a chain will return the expected data.
    """
    CRLF = b'\r\n'
    RANGE_BOUNDARY = 'One_At_A_Time_Please'
    MAX_SEND = 1500

    def __init__(self, data=None, content_length=None, content_type=None, charset=None):
        self._buffer = b''
        self._next = None

        self.chunked = False
        self.compression = False
        self.finished = False
        self.content_type = content_type
        self.content_length = content_length
        self.charset = charset
        self.send_position = 0

        if self.content_length is not None and data is not None:
            self.read_content(data)
        elif data is not None:
            self.add_content(data)

    def __len__(self):
        """ Return the actual length of the content. When subclassed, this function may be overwritten,
            e.g. FileContent returns the filesize if the file exists. For this reason, within the class
            use len(self) rather than len(self._buffer) unless the intent is carefully considered.
        :return: Number of bytes available.
        """
        if self._next is not None:
            return len(self._next)
        return len(self._buffer)

    def __getitem__(self, item):
        if self._next is not None:
            return self._next.__getitem__(item)
        return self._buffer.__getitem__(item)

    def reset(self):
        self.chunked = False
        self.compression = None
        self.content_type = None
        self.charset = None
        self.content_length = 0
        self.send_position = 0
        self._buffer = b''
        self._next = None
        self.finished = False

    def set_compression(self, method):
        if self._next is not None:
            self._next.set_compression(method)
        else:
            self.compression = method

    def compress(self):
        if self._next is not None:
            self._next.compress()
        elif self.compression == 'gzip':
            zbuf = GzipIO()
            zfile = gzip.GzipFile(mode='wb',  fileobj=zbuf, compresslevel=9)
            zfile.write(self._buffer)
            zfile.close()
            self._add_next(zbuf.getvalue())
        elif self.compression == 'deflate':
            self._add_next(zlib.compress(self._buffer))

    def decompress(self):
        if self._next is not None:
            self._next.decompress()
        elif self.compression == 'gzip':
            self._add_next(gzip.GzipFile('', 'r', 0, GzipIO(self._buffer)).read())
        elif self.compression == 'deflate':
            self._add_next(zlib.decompress(self._buffer))

    ### Adding content.
    def read_content(self, cntnt):
        """ Read content from a stream and return how many bytes have been read.
            * Chunked Transfer Encoding is handled in this function as the final content length is unknown.
            * If the final content length is known, this is honoured and content will be capped at that length.
            * If not chunked and no content length is set, we simply accept all data provided.
            As this is often used with streams of data, return the number of bytes from the provided data have
            been read.
        :param cntnt: The content to be added.
        :return: Number of bytes added.
        """
        if self._next is not None:
            return self._next.read_content(cntnt)

        consumed = 0
        if self.chunked:
            if self.CRLF not in cntnt:
                return 0
            pos = 0
            while True:
                if self.CRLF not in cntnt[pos:]:
                    return pos
                chunk_len, ignored = cntnt[pos:].split(self.CRLF, 1)
                cr = len(chunk_len) + 2
                chunk_len = int(chunk_len, 16)

                if pos + cr + chunk_len + 2 > len(cntnt):
                    break
                else:
                    pos += cr
                    if chunk_len > 0:
                        self._buffer += cntnt[pos:pos + chunk_len]
                    pos += chunk_len + 2
                if chunk_len == 0:
                    self.finished = True
                    consumed = pos
                    break
        elif self.content_length is None or self.content_length == 0:
            self.finished = True
        else:
            consumed = min(self.content_length - len(self), len(cntnt))
            self._buffer += cntnt[:consumed]
            if self.content_length == len(self):
                self.finished = True
        if self.finished:
            self.decompress()
        return consumed

    def add_content(self, cntnt):
        """ Add content to the buffer. If the data is from a network stream, read_content() should be used instead.
        :param data: The data to be added.
        :return: None.
        """
        if self._next is not None:
            return self._next.add_content(cntnt)
        self._buffer += cntnt if isinstance(cntnt, bytes) else cntnt.encode()

    @property
    def content(self):
        """ Get the full, raw content.
        :return: The objects content.
        """
        if self._next is not None:
            return self._next.content
        return self._buffer

    def decoded_content(self):
        if self._next is not None:
            return self._next.decoded_content()

        self.check_content_type()
        if self.content_type is None or self.content_type in ('text/plain', 'text/html'):
            if self.charset is not None:
                return self._buffer.decode(self.charset)
            return self._buffer.decode()

        try:
            if self.content_type in ['text/x-apple-plist+xml', 'application/x-apple-binary-plist']:
                return plist_loads(self._buffer)
            elif self.content_type == 'text/parameters':
                dd = {}
                for line in self._buffer.split(b'\n'):
                    if line == b'':
                        continue
                    k, v = line.split(b':', 1)
                    dd[k] = v.strip()
                return dd
            elif self.content_type == 'application/json':
                return json.loads(self._buffer.decode())
            elif self.content_type == 'multipart/byteranges':
                boundary = self.charset.split('=', 1)[1]
                start = self._buffer.find(b'--')
                if start == -1:
                    return []
                parts = self._buffer[start:].strip().split("--{}".format(boundary).encode())
                return [self.parse_range_multipart(p) for p in parts if len(p) > 2]
        except:
            return self._buffer

    def parse_range_multipart(self, p):
        obj = {}
        if b'\r\n\r\n' not in p:
            return {}
        hdrs, obj['content'] = p.strip().split(b'\r\n\r\n')
        for hdr in hdrs.split(self.CRLF):
            if b':' in hdr:
                k, v = hdr.decode().split(':')
                obj[k.strip()] = v.strip()
        if 'Content-Type' in obj and obj['Content-Type'] in 'text/html':
            obj['content'] = obj['content'].decode()
        return obj

    def check_content_type(self):
        if self.content_type is not None and ';' in self.content_type:
            self.content_type, self.charset = [p.strip() for p in self.content_type.split(';')]
            self.charset = self.charset.replace('charset=', '').strip()

    def header_lines(self):
        if self._next is not None:
            return self._next.header_lines()
        rv = {}

        if self.content_type is not None:
            if self.charset is None:
                rv['Content-Type'] = self.content_type
            else:
                rv['Content-Type'] = '{}; charset={}'.format(self.content_type, self.charset)
        if self.chunked:
            rv["Transfer-Encoding"] = "chunked"
        elif len(self):
            rv["Content-Length"] = "{}".format(len(self))
        if self.compression:
            rv["Content-Encoding"] = self.compression
            rv["Vary"] = 'Content-Encoding'
        return rv

    def next(self, pkt_len):
        if self._next is not None:
            return self._next.next(pkt_len)
        if len(self) == 0:
            self.finished = True
            return b''
        avail = max(self.MAX_SEND - pkt_len, len(self) - self.send_position)
        if self.chunked:
            avail -= 8
        rv = self[self.send_position: self.send_position + avail]
        self.send_position += len(rv)
        if self.chunked:
            return "{:4X}\r\n{}\r\n".format(len(rv), rv)
        return rv

    def create_ranged_output(self, ranges):
        """ If we have been asked for byte ranges, then we create them in a new Content object with
            the appropriate formatting. We need to use the current content for the ranges, but as that
            content could have been manipulated already (or be a file object), we need to access it
            correctly.
        :param ranges: List of the ranges to be processed.
        :return: None.
        """
        hdrs = {}
        if self._next is not None:
            return self._next.create_ranged_output(ranges)

        if len(ranges) == 0:
            return

        self.check_content_type()
        ct = self.content_type if len(ranges) == 1 else 'multipart/byteranges; boundary={}'.format(self.RANGE_BOUNDARY)
        cntnt = Content(content_type=ct, charset=self.charset)
        content_len = len(self)

        if len(ranges) > 1:
            for r in ranges:
                cntnt.add_content("--{}\r\nContent-Type: {}\r\nContent-Range: bytes={}\r\n\r\n".format(
                    self.RANGE_BOUNDARY, self.content_type, r.absolute_range(content_len)))
                start, end = r.absolutes(content_len)
                cntnt.add_content(self[start:end + 1])
            cntnt.add_content("--{}--\r\n".format(self.RANGE_BOUNDARY))
        else:
            start, end = ranges[0].absolutes(content_len)
            cntnt.add_content(self[start: end + 1])
            hdrs['Content-Range'] = 'bytes {}'.format(ranges[0].absolute_range(content_len))
        self._next = cntnt
        return hdrs

    def _add_next(self, data=None, content_type=None):
        self.check_content_type()
        ct = Content(data=data,
                     content_type=content_type or self.content_type,
                     charset=self.charset)
        self._next = ct


class FileContent(Content):
    def __init__(self, filename):
        Content.__init__(self)
        self.filename = filename
        self.file_handle = None
        self.exists = False
        if not os.path.exists(filename):
            return
        self.exists = True
        self.content_length = os.path.getsize(filename)
        self.content_type, ignored = mimetypes.guess_type(filename)

    def __del__(self):
        if self.file_handle is not None:
            self.file_handle.close()

    def __len__(self):
        if self._next is not None:
            return len(self._next)
        if self.exists:
            return self.content_length
        return len(self._buffer)

    def _open(self):
        """ Open the file for reading.
        :return: None
        """
        if self.file_handle is not None:
            return
        self.file_handle = open(self.filename, "rb")

    def _close(self):
        """ Close the open file handle.
        :return: None
        """
        if self.file_handle is None:
            return
        self.file_handle.close()
        self.file_handle = None

    def __getitem__(self, item):
        if isinstance(item, slice):
            self._open()
            self.file_handle.seek(item.start)
            if self.file_handle.tell() == item.start:
                return self.file_handle.read(item.stop - item.start)

        elif isinstance(item, int):
            self._open()
            self.file_handle.seek(item)
            if self.file_handle.tell() == item:
                return self.file_handle.read(1)

    def write(self):
        if self._next is not None:
            if len(self._next) == 0:
                return
        if len(self._buffer) == 0:
            return
        self._close()
        with open(self.filename, "wb") as fh:
            fh.write(self._buffer)
