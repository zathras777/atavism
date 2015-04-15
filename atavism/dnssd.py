# -*- coding: utf-8 -*-
#

# RFC 1035 - DNS
# RFC 6762 - Multicast DNS
# RFC 6763 - DNS Service Discovery

import ipaddress
import random
import time
import socket
import select
import struct
import sys

PY3 = True if sys.version_info[0] == 3 else False

QTYPE_A = 1
QTYPE_NS = 2
QTYPE_PTR = 12
QTYPE_TXT = 16
QTYPE_AAAA = 28
QTYPE_SRV = 33
QTYPE_OPT = 41
QTYPE_NSEC = 47
QTYPE_ALL = 255

QCLASS_IN = 1
QCLASS_NONE = 254
QCLASS_ANY = 255

FLAGS_RCODE = (1 << 0) | (1 << 1) | (1 << 2) | (1 << 3)
FLAGS_Z = (1 << 4) | (1 << 5) | (1 << 6)
FLAGS_RA = 1 << 7
FLAGS_RD = 1 << 8
FLAGS_TC = 1 << 9
FLAGS_AA = 1 << 10  # authoritative
FLAGS_OPCODE = (1 << 11) | (1 << 12) | (1 << 13) | (1 << 14)
FLAGS_QR = 1 << 15  # response

OPCODE_QUERY = 1
OPCODE_STATUS = 2
OPCODE_NOTIFY = 4
OPCODE_NOTIFY = 5


class PacketError(Exception):
    pass


class Packet(object):
    """ Class to represnt a packet received from or being sent via the network.
        Contains all the data and functions to operate on the data.
        The data is stored as bytes internally but returned as str objects normally.
    """
    def __init__(self, data=None):
        self.txt_offsets = {}
        self.data = b''
        self.add_data(data)

    def reset(self):
        self.data = b''

    def add_data(self, data):
        if data is None or len(data) == 0:
            return
        if isinstance(data, str):
            self.data += data.encode() if PY3 else data
        elif isinstance(data, bytes):
            self.data += data
        else:
            raise PacketError("Trying to add data of type '{}' to the buffer failed.".format(type(data)))

    def __len__(self):
        return len(self.data)

    def read_name(self, pos=0):
        """ Read an encoded name from the data. The name will consist of a series of pieces,
            each of which may be a string or an offset to the string.
            If a name cannot be read, a PacketError exception will be raised.
        :param pos: The position within the data to start reading the name.
        :return: The number of bytes of the stream read, the namename.
        """
        bytes, name, eos = self._read_name(pos)
        if not eos:
            raise PacketError("Unable to read a name from position {}".format(pos))
        return bytes, name

    def _read_name(self, pos):
        """ Internal function to get a name, or portion of a name from the data.
            May be called recursively.
        """
        start = pos
        eos = False
        parts = []
        while True:
            len_or_offset = ord(self.data[pos]) if not PY3 else self.data[pos]
            if len_or_offset == 0:
                pos += 1
                eos = True
                break

            if len_or_offset & 0xc0 == 0:
                pos += 1
                # simple length of string that follows
                if len_or_offset == 0:
                    eos = True
                else:
                    utf8 = self.read_utf8(pos, len_or_offset)
                    pos += len_or_offset
                    parts.append(utf8)

            elif len_or_offset & 0xc0 == 0xC0:
                # offset to string
                offset = struct.unpack("!H", self.data[pos:pos+2])[0]
                offset ^= 0xc000
                pos += 2
                ignored, utf8, eos = self._read_name(offset)
                parts.append(utf8)
                if eos:
                    break

            else:
                raise PacketError("Bad domain name at {0:X}".format(self.data[pos]))
        return pos - start, '.'.join(parts), eos

    def write_name(self, name):
        """ Write an encoded name into the data stream.
        :param name: The name to be encoded.
        :returns: The number of bytes added to the data stream.
        """
        # Do we have the entire name available?
        if name in self.txt_offsets:
            offs = self.txt_offsets[name]
            offs |= (1 << 15)
            offs |= (1 << 14)
            self.pack("!H", offs)
            return 2
        # Add the
        start = len(self.data)
        parts = name.split('.')
        null_needed = True
        for i in range(len(parts)):
            pstr = ".".join(parts[i:])
            if pstr in self.txt_offsets:
                offs = self.txt_offsets[pstr]
                offs |= (1 << 15)
                offs |= (1 << 14)
                self.pack("!H", offs)
                null_needed = False
                break
            else:
                self.txt_offsets[pstr] = len(self.data)
                utf8_string = parts[i].encode('utf-8')
                self.pack('!B', len(utf8_string))
                self.data += utf8_string
        if null_needed:
            self.pack("!b", 0)
        return len(self.data) - start

    def read_utf8(self, pos, len):
        """ Attempt to read a utf-8 string from the stored data, blen bytes starting at
            bpos offset into the stream. Return the number of bytes of the stream read
            to the end of the string and the string.
        """
        return self.data[pos: pos + len].decode('utf-8')

    def ipaddress(self, version, pos, nbytes):
        if version == 4:
            return ipaddress.IPv4Address(self.data[pos:pos+nbytes])
        elif version == 6:
            return ipaddress.IPv6Address(self.data[pos:pos+nbytes])
        return None

    def pack(self, fmt, *args, **kwargs):
        """ Attempt to write packed data into the data. This is simply appended to the end of the
            data.
        :param fmt: The format of the data to be written.
        :param data: Data to be written.
        :return: Number of bytes written.
        """
        blen = struct.calcsize(fmt)
        if PY3:
            data = [a.encode() if isinstance(a, str) else a for a in args]
            pdata = struct.pack(fmt, *data)
        else:
            pdata = struct.pack(fmt, *args)

        if 'pos' in kwargs:
            pos = kwargs['pos']
            if 0 < pos > len(self.data):
                raise PacketError("Attempt to pack data outside of available data (@ {} but data is {} bytes)".format(pos, len(self.data)))
            self.data = self.data[:pos] + pdata + self.data[pos+blen:]
        else:
            self.data += pdata
        return blen

    def unpack(self, pos, fmt):
        """ Attempt to unpack a binary format from the data. If this returns a single item then that
            item is returned, but if more than one value is unpacked a list of those values will be
            returned.
            i.e. unpack(..., "b") will return a byte value, unpack(..., '"bb") will return a list of 2 byte
                 values.
            NB If the position specified is outside the size of the buffer, a PacketError exception is raised.
        :param pos: Position within buffer to start
        :param fmt: Format to be unpacked
        :return: Length of bytes read and value(s).
        """
        blen = struct.calcsize(fmt)
        if pos < 0 or pos + blen > len(self.data):
            raise PacketError("Invalid position specified for unpack.")
        parts = [n.decode() if isinstance(n, bytes) else n for n in struct.unpack(fmt, self.data[pos:pos + blen])]
        if len(parts) == 1:
            return blen, parts[0]
        return blen, parts


class MDNSResponse(object):
    TYPE_NAMES = {
        1: 'A',
        12: 'PTR',
        16: 'TXT',
        28: 'AAAA',
        33: 'SRV',
    }

    def __init__(self, data=None):
        self.packet = Packet(data)

        self.pos = 0
        self.questions = []
        self.answers = []
        self.nameservers = []
        self.additional = []

        self.pos, parts = self.packet.unpack(0, "!HHHHHH")
        self.id, self.flags, self.qdcount, self.ancount, self.nscount, self.arcount = parts

        # Is it a response? Do we have answers?
        if self.flags & FLAGS_QR == 0 or self.ancount == 0 or self.flags & FLAGS_RCODE != 0:
            return
        self.parse_records()

    @property
    def is_valid(self):
        return len(self.answers) != 0

    @property
    def has_error(self):
        return self.flags & FLAGS_RCODE != 0

    def is_applicable(self, qry):
        qnames = [q['qname'] for q in qry.questions]
        for a in self.answers:
            if a['qname'] in qnames:
                return True
            if ".".join(a['qname'].split('.')[1:]) in qnames:
                return True
        return False

    @property
    def is_authoritative(self):
        return self.flags & FLAGS_AA != 0

    def parse_records(self):
        for q in range(self.qdcount):
            n, qname = self.packet.read_name(self.pos)
            qu = {'qname': qname}
            self.pos += n
            n, (qu['qtype'], qu['qclass']) = self.packet.unpack(self.pos, "!HH")
            self.pos += n
            self.questions.append(qu)

        self._parse_section(self.ancount, self.answers)
        self._parse_section(self.nscount, self.nameservers)
        self._parse_section(self.arcount, self.additional)

    def _parse_section(self, num, store):
        for a in range(num):
            n, qname = self.packet.read_name(self.pos)
            self.pos += n

            n, (typ, cls, ttl, rdlength) = self.packet.unpack(self.pos, "!HHiH")
            rec = {'qname': qname, 'qtype': typ, 'qclass': cls, 'ttl': ttl}
            self.pos += n

            if typ == QTYPE_SRV:
                n, (priority, weight, port) = self.packet.unpack(self.pos, "!HHH")
                self.pos += n
                n, name = self.packet.read_name(self.pos)
                rec['SRV'] = {'port': port,
                              'name': name,
                              'priority': priority,
                              'weight': weight}
                self.pos += n
            elif typ == QTYPE_A:
                rec['A'] = self.packet.ipaddress(4, self.pos, rdlength)
                self.pos += rdlength
            elif typ == QTYPE_AAAA:
                rec['AAAA'] = self.packet.ipaddress(6, self.pos, rdlength)
                self.pos += rdlength
            elif typ == QTYPE_PTR:
                n, rec['PTR'] = self.packet.read_name(self.pos)
                self.pos += n
            elif typ == QTYPE_TXT:
                rec['TXT'] = self.packet.data[self.pos: self.pos + rdlength]
                self.pos += rdlength
            elif typ == QTYPE_OPT:
                rec['OPT'] = self.packet.data[self.pos: self.pos + rdlength]
                self.pos += rdlength
            else:
                self.pos += rdlength
            store.append(rec)


class MDNSQuery(object):
    MAX_ANSWERS = 24

    def __init__(self, questions=None, answers=None):
        self.questions = questions or []
        self.answers = answers or []
        self.packet = Packet()
        self.pkt_id = random.getrandbits(16)
        self.flags = 0

    def __len__(self):
        return len(self.questions)

    def add_question(self, qname, qtype=QTYPE_ALL, qclass=QCLASS_IN):
        self.questions.append({'qname': qname, 'qtype': qtype, 'qclass': qclass})

    def add_answer(self, qname, ptr, qtype, qclass=QCLASS_IN, ttl=0):
        self.answers.append({'qname': qname, 'ptr': ptr, 'qtype': qtype, 'qclass': qclass, 'ttl': ttl})

    def packet_data(self):
        """ Create the packets we will send. There could be more than 1 packet if we have a
            large number of answers to include. Answers are included to reduce network traffic.
            As the query is created, then used for each sending attempt, we increment the pkt_id
            each time we create the packets. All packets
        :return: A list of packets.
        """
        idx = 0
        packets = []
        while idx <= len(self.answers):
            flags = self.flags
            pkt = Packet()

            if len(self.answers) - idx >= self.MAX_ANSWERS:
                flags |= FLAGS_TC

            # We only include the question on the initial packet...
            qc = len(self.questions) if idx == 0 else 0
            ac = min(self.MAX_ANSWERS, len(self.answers) - idx)

            if qc + ac == 0:
                break

            pkt.pack("!HHHHHH", self.pkt_id, flags, qc, ac, 0, 0)

            for q in self.questions[:qc]:
#                print("  Q: {}".format(q))
                pkt.write_name(q['qname'])
                pkt.pack("!HH", q['qtype'], q['qclass'])

            for a in self.answers[idx: idx + ac]:
#                print("  A: {}".format(a))
                pkt.write_name(a['qname'])
                pkt.pack("!HHI", a['qtype'], a['qclass'], a['ttl'])
                rdpos = len(pkt)
                pkt.data += b'  '
                ptrlen = pkt.write_name(a['ptr'])
                pkt.pack("!H", ptrlen, pos=rdpos)

            packets.append(pkt.data)
            if ac == 0:
                break
            idx += ac
        return packets


class MDNSServiceDiscoveryError(Exception):
    pass


class MDNSServiceDiscovery(object):
    IP4_MULTICAST = ipaddress.IPv4Address(u'224.0.0.251')
    IP6_MULTICAST = ipaddress.IPv6Address(u'FF02::FB')
    MULTICAST_PORT = 5353

    def __init__(self, qname=None, qtype=QTYPE_ALL):
        self.ip_version = 4
        self.ttl = 2
        self.timeout = 10
        self.devices = {}

        self.interface = self.find_interfaces()
        self.query = MDNSQuery()
        if qname is not None:
            self.query.add_question(qname.strip(), qtype)

    def find_interfaces(self):
        """ Find the local interface(s) that we will send via.
            Presently I have no way of finding a local IPv6 interface, so just use
            IPv4.
            An MDNSServiceDiscoveryError will be raised if the local interface can't be found.
        :return: The interface to be used.
        """
        try:
            x = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            x.connect(('1.2.3.4', 56))
            interface = x.getsockname()[0]
            x.close()
        except socket.error as e:
            raise MDNSServiceDiscoveryError("Unable to find local interface.")
        return interface

    def find_devices(self):
        now = time.time()
        nxt = now
        last = now + self.timeout
        delay = 1

        sock = self.make_socket()
        while last > now:
            now = time.time()

            if now >= nxt:
                for data in self.query.packet_data():
                    sock.sendto(data, 0, (str(self.IP4_MULTICAST), self.MULTICAST_PORT))
                nxt += delay
                delay *= 2

            r, w, e = select.select([sock], [], [sock], 0.5)
            if not r:
                continue

            data, addr = sock.recvfrom(16384)
            if data:
                resp = MDNSResponse(data)
                # We only want responses to our queries, not everyone elses!
                if not resp.is_valid:
                    continue

                if not resp.is_applicable(self.query):
                    continue

                for a in resp.answers:
                    if 'PTR' not in a:
                        continue
#                    print("A: {}", a)


                    self.query.add_answer(a['qname'], a['PTR'], a['qtype'], a['qclass'], a['ttl'])
                    if a['PTR'] not in self.devices:
                        dev = {'PTR': a['PTR']}
                        for ad in resp.additional\
                                :
#                            print("    ADD: {}".format(ad))
                            for poss in ('A', 'AAAA', 'TXT', 'SRV'):
                                if poss in ad:
                                    dev[poss] = ad[poss]
                        self.devices[a['PTR']] = dev

#        print(self.devices)
        sock.close()

        return len(self.devices) > 0

    def make_socket(self):
        """ Open a socket that can be used for sending and receiving multicast packets.
            If a socket cannot be created or setup then an MDNSServiceDiscoveryError is raised.
        :return: The created socket.
        """
        host = socket.inet_aton(self.interface)

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

            sock.setblocking(0)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

            sock.bind((str(self.IP4_MULTICAST), self.MULTICAST_PORT))

            sock.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_TTL, struct.pack('B', self.ttl))
            sock.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF, host)
            sock.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_LOOP, 0)

        except:
            print(sys.exc_info())
            raise MDNSServiceDiscoveryError("Unable to create a suitable socket for MDNS")

        return sock
