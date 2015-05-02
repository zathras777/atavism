import os
import unittest
from atavism.http11.client import HttpClient, HttpClientError
from atavism.video import HLSVideo


class TestDNS(unittest.TestCase):
    SAMPLE_VIDEOS = [
        {
            'host': 'cdn.clipcanvas.com',
            'url': '/sample/clipcanvas_14348_offline.mp4',
            'filename': os.path.join('.', 'tests', 'sample_01.mp4')
        },
        {
            'host': 'download.wavetlan.com',
            'url': '/SVV/Media/HTTP/mkv/validationsuite/test2.mkv',
            'filename': os.path.join('.', 'tests', 'sample_02.mkv')
        },
        {
            'host': 'download.wavetlan.com',
            'url': '/SVV/Media/HTTP/mkv/MP4_Xvid_AAC-LC(mkvmerge).mkv',
            'filename': os.path.join('tests', 'sample_03.mkv')
        }
    ]

    @classmethod
    def setUpClass(cls):
        """ Use the sample video @ http://cdn.clipcanvas.com/sample/clipcanvas_14348_offline.mp4
        """
        for sv in cls.SAMPLE_VIDEOS:
            if not os.path.exists(sv['filename']):
                print("Downloading sample video from {}. Please be patient...".format(sv['host']))
                http = HttpClient(sv['host'])
                if http.verify():
                    try:
                        http.download_file(sv['url'], sv['filename'])
                    except HttpClientError as e:
                        print(e)
                        pass
                else:
                    print("Unable to connect to {}".format(sv['host']))

    def test_001_hls(self):
        h = HLSVideo(self.SAMPLE_VIDEOS[0]['filename'])

        self.assertEqual(h.video_width(), 1024)
        self.assertEqual(h.video_height(), 576)
        self.assertTrue(h.has_audio())
        self.assertEqual(h.audio_streams(), 1)
        self.assertFalse(h.needs_resize(1920, 1080))
        self.assertTrue(h.needs_resize(920, 517))

    def test_002_hls(self):
        h = HLSVideo(self.SAMPLE_VIDEOS[1]['filename'])
        self.assertEqual(h.video_width(), 1024)
        self.assertEqual(h.video_height(), 576)
        self.assertTrue(h.has_audio())
        self.assertEqual(h.audio_streams(), 1)
        self.assertFalse(h.needs_resize(1920, 1080))
        self.assertTrue(h.needs_resize(920, 517))
#        self.assertTrue(h.create_hls(920, 517))

    def test_003_hls(self):
        h = HLSVideo(self.SAMPLE_VIDEOS[2]['filename'])
        self.assertEqual(h.video_width(), 320)
        self.assertTrue(h.create_hls())
