class Range(object):
    def __init__(self, tpl):
        self.start = int(tpl[0]) if tpl[0] is not None and tpl[0] != b'' else None
        self.end = int(tpl[1]) if tpl[1] is not None and tpl[1] != b'' else None
        if self.start is None and self.end is not None and self.end > 0:
            self.end *= -1

    def __str__(self):
        return "Byte Range: {} - {}".format(self.start, self.end)

    def __len__(self, cl=0):
        if self.start is None and self.end is not None:
            return self.end * -1
        elif self.end is None:
            return cl - self.start
        return self.end - self.start + 1

    def header(self):
        r = ''
        if self.start is not None:
            r += '{}-'.format(self.start)
        if self.end is not None:
            r += "{}".format(self.end)
        return r

    def from_content(self, content):
        """ Try and get the range from the supplied content. If it isn't possible,
            return None.
        :param content: The content stream to extract the range from.
        :return: The extracted content or None.
        """
        csz = len(content)
        if self.end is not None:
            if self.end < 0 and csz < self.end * -1:
                print("not big enough")
                return None
            if self.end > csz:
                print("end > content length")
                return None
        else:
            if self.start > csz:
                print("start > content length")
                return None
        if self.end is None:
            return content[self.start:]
        elif self.start is None:
            return content[self.end:]
        return content[self.start: self.end + 1]

    def absolutes(self, clen):
        start = self.start
        if self.start is None:
            if self.end < 0:
                return clen + self.end, clen - 1
            start = 0
        end = clen
        if self.end is not None:
            if self.end < 0:
                end = clen + self.end - 1
            else:
                end = self.end
        if end < start:
            end = start
        return start, end

    def absolute_range(self, clen):
        start, end = self.absolutes(clen)
        return "{}-{}/{}".format(start, end, clen)
