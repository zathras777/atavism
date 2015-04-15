import unittest
from atavism.dnssd import Packet, PacketError, MDNSQuery, QTYPE_ALL, MDNSServiceDiscovery, MDNSResponse, QTYPE_TXT, \
    QTYPE_SRV


class TestDNS(unittest.TestCase):
    def test_001_packet(self):
        p = Packet("hello world")
        self.assertEqual(len(p), 11)
        self.assertRaises(PacketError, p.unpack, -1, "5s")
        self.assertEqual(p.unpack(0, "5s"), (5, "hello"))
        self.assertEqual(p.read_utf8(6, 5), "world")

        self.assertEqual(p.pack("2s", "!!"), 2)
        self.assertEqual(len(p), 13)
        self.assertEqual(p.read_utf8(6, 7), "world!!")

        p.write_name("qname")
        # We expect the length to increase by 7
        self.assertEqual(len(p), 20)
        self.assertEqual(p.read_name(13), (7, "qname"))
        # reset it...
        p.reset()
        self.assertEqual(len(p), 0)
        self.assertEqual(p.data, b'')

    def test_002_query(self):
        m = MDNSQuery()
        self.assertEqual(len(m), 0)
        m.add_question('_airplay._tcp.local', QTYPE_ALL)
        self.assertEqual(len(m), 1)
        self.assertEqual(len(m.packet_data()), 1)

    def test_003_response(self):
        resp_data = b'\x00\x00\x84\x00\x00\x00\x00\x01\x00\x00\x00\x04\x08\x5f\x61\x69\x72\x70\x6c\x61\x79\x04\x5f\x74\x63'
        resp_data += b'\x70\x05\x6c\x6f\x63\x61\x6c\x00\x00\x0c\x00\x01\x00\x00\x11\x94\x00\x0b\x08\x41\x70\x70\x6c\x65'
        resp_data += b'\x20\x54\x56\xc0\x0c\x08\x41\x70\x70\x6c\x65\x2d\x54\x56\xc0\x1a\x00\x01\x80\x01\x00\x00\x00\x78'
        resp_data += b'\x00\x04\xc0\xa8\x01\x41\xc0\x36\x00\x1c\x80\x01\x00\x00\x00\x78\x00\x10\xfe\x80\x00\x00\x00\x00'
        resp_data += b'\x00\x00\x0c\xd6\xed\x24\x44\xe1\x8f\xcf\x00\x00\x29\x05\xa0\x00\x00\x00\x00\x00\x18\x00\x04\x00'
        resp_data += b'\x14\x00\x41\x68\xd9\x3c\x81\xcf\x37\x68\xd9\x3c\x81\xcf\x37\x00\x00\x00\x00\x00\x00\x00\x00\x29'
        resp_data += b'\x05\xa0\x00\x00\x00\x00\x00\x0c\xfd\xea\x00\x08\xb6\x97\x14\x6a\x7d\x88\x0c\x11'

        r = MDNSResponse(resp_data)
        self.assertTrue(r.is_valid)
        self.assertTrue(r.is_authoritative)
        self.assertEqual(len(r.answers), 1)
        self.assertEqual(len(r.additional), 4)
        self.assertEqual(r.answers[0]['PTR'], 'Apple TV._airplay._tcp.local')
        self.assertEqual(r.answers[0]['ttl'], 4500)

#    def test_004_discovery(self):
#        sd = MDNSServiceDiscovery('_airplay._tcp.local')
#        self.assertEqual(len(sd.query), 1)
#        sd.find_devices()
