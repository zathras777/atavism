import unittest
from ipaddress import IPv4Address, IPv6Address
from atavism.devices import AirplayDevice


class TestDevices(unittest.TestCase):
    def test_001_device(self):
        dev_dict = {'A': IPv4Address(u'192.168.1.65'),
                    'AAAA': IPv6Address(u'fe80::dd6:ee24:22e1:8fcf'),
                    'PTR': u'Apple TV._airplay._tcp.local'}
        dev = AirplayDevice(dev_dict)
        self.assertEqual(dev.name, 'Apple TV')
        print(dev)
        print(dev.features())