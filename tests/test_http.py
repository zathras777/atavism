import os
import unittest
from atavism.http11.client import HttpClient
from atavism.http11.content import Content, FileContent
from atavism.http11.headers import Headers
from atavism.http11.objects import HttpRequest


class TestHeaders(unittest.TestCase):
    def test_001_creation(self):
        hb = Headers()
        self.assertEqual(len(hb), 0)
        self.assertEqual(len(hb.headers), 0)
        self.assertFalse(hb.finished)

    def test_002_input(self):
        input = [
            [
                (b'GET / HTTP/1.1\r\n', 16, False),
                (b'Host: 192.168.1', 15, False),
                (b'.1\r\n\r\n', 6, True),
            ],
            [
                (b'GET / HTTP/1.1\r\n', 16, False),
                (b'Host: 192.168.1', 15, False),
                (b'.1\r\n', 4, False),
                (b'\r\nHello World', 2, True)
            ]
        ]
        for inp_set in input:
            hb = Headers()
            for inp in inp_set:
                self.assertEqual(hb.read_content(inp[0]), inp[1],
                                 "read_content('{}') should have returned {}".format(inp[0], inp[1]))
                self.assertEqual(hb.finished, inp[2])
            self.assertEqual(len(hb), 33)
            self.assertEqual(hb.status_line, 'GET / HTTP/1.1')
            self.assertEqual(len(hb.headers), 1)

    def test_003_output(self):
        hb = Headers()
        hb.add_header('Host', '127.0.0.1')
        self.assertEqual(len(hb.headers), 1)
        self.assertIn("Host: 127.0.0.1\r\n\r\n", str(hb))
        hb.add_headers({'User-Agent': 'Test/0.1',
                        'Accept-Encoding': 'identity'})
        self.assertEqual(len(hb.headers), 4)
        hdr_str = str(hb)
        self.assertEqual(len(hdr_str.split("\r\n")), 6)
        self.assertIn("Accept-Encoding: identity\r\n", hdr_str)


class TestContent(unittest.TestCase):
    def test_001_creation(self):
        ct = Content()
        self.assertFalse(ct.finished)
        self.assertIsNone(ct.content_type)
        self.assertIsNone(ct.content_length)

        ct2 = Content(content_length=12, content_type='text/plain')
        self.assertFalse(ct2.finished)
        self.assertEqual(ct2.content_length, 12)

    def test_002(self):
        cases = [
            ([b'Hello World!'], 12, 'text/plain', 'Hello World!'),
            ([b'{"origin"', b': "127.0.0.1"}'], 23, 'application/json', {'origin': '127.0.0.1'}),
        ]
        for c in cases:
            ct = Content(data=c[0][0], content_length=c[1], content_type=c[2])
            self.assertEqual(ct.finished, True if len(c[0]) == 1 else False)
            self.assertEqual(len(ct), len(c[0][0]))
            for n in range(1, len(c[0])):
                ct.read_content(c[0][n])
            self.assertTrue(ct.finished)
            self.assertEqual(ct.decoded_content(), c[3])

    def test_003(self):
        ct = Content(data=b'012345678901234567890')
        self.assertEqual(len(ct), 21)
        self.assertEqual(ct[0:2], b'01')


class TestFileContent(unittest.TestCase):
    def test_001(self):
        fc = FileContent('tests/test_http.py')
        self.assertEqual(len(fc), os.path.getsize('tests/test_http.py'))
        self.assertEqual(fc[0:10], b'import os\n')

    def test_002(self):
        fn = 'tests/hello_world.txt'
        if os.path.exists(fn):
            os.unlink(fn)
        fc = FileContent(fn)
        self.assertEqual(len(fc), 0)
        fc.add_content(b'Hello World!')
        self.assertEqual(len(fc), 12)
        fc.write()
        self.assertTrue(os.path.exists(fn))
        self.assertEqual(os.path.getsize(fn), 12)


class HttpbinTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = HttpClient('httpbin.org')

    def test_001_ip(self):
        self.assertTrue(self.http.verify())
        self.assertIsNotNone(self.http.simple_request('/ip'))

    def test_002_headers(self):
        self.http.user_agent = 'Test/0.1'
        hdrs = self.http.simple_request('/headers')
        self.assertIsInstance(hdrs, dict)
        self.assertIn('headers', hdrs)
        self.assertIn('User-Agent', hdrs['headers'])
        self.assertEqual(hdrs['headers']['User-Agent'], 'Test/0.1')

    def test_003_post(self):
        resp = self.http.post_data('/post', {'a': 1, 'b': 2})
        self.assertEqual(resp.code, 200)
        self.assertEqual(resp.get('content-type'), 'application/json')
        json_data = resp.decoded_content()
        self.assertIn('data', json_data)
        self.assertEqual(json_data['form'], {'a': '1', 'b': '2'})
        self.assertEqual(json_data['headers']['Content-Length'], '7')
        self.assertIn('files', json_data)

    def test_004_stream(self):
        lines = self.http.request('/stream/10')
        self.assertEqual(lines.code, 200)
        self.assertEqual(len(lines.decoded_content().split(b'\n')), 11)

    def test_005_gzip(self):
        gzip = self.http.request('/gzip')
        data = gzip.decoded_content()
        self.assertEqual(type(data), dict)
        self.assertIn('gzipped', data)
        self.assertTrue(data["gzipped"])
        self.assertNotEqual(gzip._content.content_length, len(gzip._content))

    def test_006_deflate(self):
        obj = self.http.request('/deflate')
        data = obj.decoded_content()
        self.assertEqual(type(data), dict)
        self.assertIn('deflated', data)
        self.assertTrue(data["deflated"])
        self.assertNotEqual(obj._content.content_length, len(obj._content))

    def test_007_drip(self):
        resp = self.http.request('/drip', {'numbytes': 1500,'duration': 5, 'code': 200})
        self.assertEqual(resp.code, 200)
        self.assertEqual(len(resp), 1500)


class RangeRequestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = HttpClient('www.lysator.liu.se')

    def test_001(self):
        # http://www.lysator.liu.se/pinball/expo/
        req = HttpRequest(path='/pinball/expo/')
        req.add_range(0, 61)

        resp = self.http.send_request(req)
        self.assertEqual(resp.code, 206)
        self.assertEqual(len(resp), 62)
        self.assertEqual(resp.decoded_content(), '''<html>
<head>
<base="http://www.lysator.liu.se/pinball/expo/">''')

    def test_002(self):
        # http://www.lysator.liu.se/pinball/expo/
        req = HttpRequest(method='GET', path='/pinball/expo/')
        req.add_range(0, 61)
        req.add_range(end=-10)

        resp = self.http.send_request(req)
        self.assertEqual(resp.code, 206)
        parts = resp.decoded_content()
        self.assertEqual(len(parts), 2)
        self.assertIn('Content-Type', parts[0])
        self.assertIn('Content-Range', parts[0])

        self.assertEqual(parts[0]['content'], '''<html>
<head>
<base="http://www.lysator.liu.se/pinball/expo/">''')
        self.assertEqual(parts[1]['content'], '''>
</html>''')
