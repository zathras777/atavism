from datetime import datetime


class Headers(object):
    CRLF = b"\r\n"
    EOH = b"\r\n\r\n"

    def __init__(self, data=None, status_line=None):
        self.buffer = data or b''
        self.finished = False
        self.status_line = status_line
        self.headers = {}

    def __len__(self):
        return len(self.buffer)

    def read_content(self, cntnt):
        """ Read data from a stream until we have a complete set of headers.
        :param cntnt: Stream data to read.
        :return: Number of bytes of stream that have been used.
        """
        if self.finished:
            return 0
        consumed = 0
        idx = cntnt.find(self.EOH)
        if idx >= 0:
            consumed = idx + 4
            self.buffer += cntnt[:idx]
            self.finished = True
        else:
            consumed = len(cntnt)
            olen = len(self.buffer)
            self.buffer += cntnt
            idx = self.buffer.find(self.EOH)
            if idx >= 0:
                consumed = idx - olen + 4
                self.buffer = self.buffer[:idx]
                self.finished = True
        if self.finished:
            self.parse_headers()
        return consumed

    def add_header(self, key, value):
        self.headers[key] = value

    def add_headers(self, hdr_dict):
        if hdr_dict is not None and len(hdr_dict) > 0:
            self.headers.update(hdr_dict)

    def parse_headers(self):
        """ Parse headers from a request.
        :param hdr_data: The header data, excluding the final \r\n\r\n
        :return: No
        """
        self.headers = {}
        lines = self.buffer.split(self.CRLF)
        self.status_line = lines[0].decode()
        for line in lines[1:]:
#            print(":: {}".format(line))
            if b':' in line:
                key, value = line.split(b':', 1)
                self.headers[key.decode()] = value.strip().decode()
            else:
                print("Malformed header line: {}".format(line))

    def __str__(self):
        lines = [self.status_line] if self.status_line is not None else []
        self.headers['Date'] = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
        for k in sorted(self.headers):
            lines.append("{}: {}".format(k, self.headers[k]))
        return "\r\n".join(lines) + "\r\n\r\n"

    def get(self, key, default=None):
        """ Get a header value or default, regardless of case.
        :param key: The header key to get. Case insensitive.
        :param default: The value to return if the header s not present. Defaults to None.
        :return: The value of the header or the default value (if no default is given, None).
        """
        key = key.decode() if isinstance(key, bytes) else key
        for k in self.headers.keys():
            kk = k if not isinstance(k, bytes) else k.decode()
            if kk.lower() == key.lower():
                v = self.headers[k]
                return int(v) if v.isdigit() else v
        return default
