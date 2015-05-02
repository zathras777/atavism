from datetime import datetime


def stripped_split(ss, c, n=-1):
    return [p.strip() for p in ss.split(c, n)]


class Cookie(object):
    def __init__(self, path=None, key=None, value=None, domain=None, expires=None, max_age=None, secure=False):
        self.path = path
        self.key = key
        self.value = value
        self.expires = expires
        self.domain = domain
        self.max_age = max_age
        self.secure = secure
        self.http_only = False

    def __eq__(self, other):
        if other.path != self.path or other.key != self.key or other.domain != self.domain:
            return False
        return True

    def __str__(self):
        base = ['{}={}'.format(self.key or '', self.value or '')]
        if self.path is not None:
            base.append("Path={}".format(self.path))
        if self.domain is not None:
            base.append("Domain={}".format(self.domain))
        if self.http_only:
            base.append('HttpOnly')

        return "; ".join(base)

    def set_expires(self, dtstr):
        self.expires = datetime.strptime(dtstr, "%a, %d-%b-%Y %H:%M:%S %Z")

    def as_header(self):
        return "{}={}".format(self.key, self.value)

    def is_relevant(self, _path=None):
        if self.expires is not None:
            if self.expires < datetime.utcnow():
                return False

        if _path is None:
            return False
        if self.path is None or _path == '/':
            return True

        if _path[:len(self.path)].lower() == self.path.lower():
            return True

        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __lt__(self, other):
        if len(self.path) == len(other.path):
            return self.key < other.key
        return len(self.path) < len(other.path)

    def __gt__(self, other):
        return len(self.path) > len(other.path)


class CookieJar(object):
    def __init__(self):
        self.cookies = []

    def __len__(self):
        return len(self.cookies)

    def add_cookie(self, _cookie):
        for cc in self.cookies:
            if cc == _cookie:
                cc.value = _cookie.value
                return
        self.cookies.append(_cookie)

    def __getitem__(self, item):
        for c in self.cookies:
            if c.key == item:
                return c.value
        return None

    def get_cookie(self, item):
        for c in self.cookies:
            if c.key == item:
                return c
        return None

    def parse_set_cookie(self, hdr_string):
        if '=' not in hdr_string:
            return
        parts = stripped_split(hdr_string, ';')
        c = Cookie()
        c.key, c.value = stripped_split(parts[0], '=', 1)
        for p in parts[1:]:
            if p == 'HttpOnly':
                c.http_only = True
                continue

            k, v = stripped_split(p, '=', 1)
            if k.lower() == 'expires':
                c.set_expires(v)
            else:
                setattr(c, k.lower(), v)
        self.add_cookie(c)

    def check_cookies(self, http_obj):
        cookies = http_obj.get('set-cookie')
        if cookies is None:
            return
        for c_str in cookies:
            self.parse_set_cookie(c_str)

    def get_cookies(self, _path):
        matched = []
        for c in self.cookies:
            if c.is_relevant(_path):
                matched.append(c)
        if len(matched) == 0:
            return None
        return '; '.join([c.as_header() for c in sorted(matched)])
