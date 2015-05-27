import logging
import socket
import ssl
from threading import Thread, Event
from time import sleep, time
import re
import math
from struct import pack
from atavism.chromecast import ChromecastClient
from atavism.http11.client import HttpClient


class DeviceError(Exception):
    pass


def show_progress(current, duration):
    interval = 2
    if current > 0:
        n = (current / duration) * 100
        bar = "#" * int(math.floor(n / 2.0))
    elif current == duration:
        bar = ' Completed'
        n = 100.0
        interval = 0
    else:
        bar = ' Buffering...'
        n = 0.0
    print('\r   Playback: [%-50s] %7.03f%%' % (bar, n))
    return interval


class AirplayDevice:
    SCRUB_RE = re.compile(b"([a-z]+)\: ([0-9\.]+)")
    UPDATE_INTERVAL = 5

    def __init__(self, device=None):
        self.name = None
        self.info = None
        self.output = (-1, -1)
        if device is None:
            return

        self.ptr = device.get('PTR')
        self.host = device.get('A')
        self.host6 = device.get('AAAA')
        self.port = device.get('port', 7000)

        self.http = HttpClient(self.host, self.port)

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.getLogger().level)

        if self.ptr is not None:
            self.name = self.ptr.split('.')[0]
            self.get_info()

    @property
    def width(self):
        return self.output[0]

    @property
    def height(self):
        return self.output[1]

    def get_info(self):
        if self.host is None and self.host6 is None:
            raise DeviceError("Unable to get device information as no IPv4 or IPv6 address available?")

        self.info = self.http.simple_request('/server-info')
        if self.info is None:
            return
        self.output = (1920, 1080) if '3' in self.info['model'] else (1280, 720)

    def __str__(self):
        if self.info is None:
            return "Unknown device @ {}:{}".format(self.host, self.port)
        return "{} [{}]  {}x{} @ {}:{}".format(self.name or 'Unknown',
                                               self.info.get('model', 'Unknown'),
                                               self.output[0], self.output[1],
                                               self.host, self.port)

    def features(self):
        if self.info is None or 'features' not in self.info:
            return 'Unknown'
        supported = []
        f_list = ['Video', 'Photo', 'VideoFairPlay', 'VideoVolumeControl', 'VideoHTTPLiveStreams',
                  'Slideshow', '6', 'Screen', 'ScreenRotate', 'Audio', 'AudioRedundant',
                  'FPSAPv2pt5_AES_GCM', 'PhotoCaching', '12', '13', '14', '15', '16', '17',
                  '18', '19', '20', '21', '22', '23', '24', '25', '26', '27', '28', '29',
                  '30', '31']
        for i in range(len(f_list)):
            if self.info['features'] & 1 << i != 0:
                supported.append(f_list[i])
        return ",".join(supported)

    @property
    def supports_streaming(self):
        if self.info is None or 'features' not in self.info:
            return False
        return self.info.get('features', 0) & 1 << 4 != 0

    def stop_video(self):
        resp = self.http.post_data('/stop')
        return resp.code == 200

    def play_video(self, video_srv):
        self.stop_video()

        pdata = {'Content-Location': video_srv.url, 'Start-Position': 0}
        resp = self.http.post_data('/play', data=pdata, ct='text/parameters')
        if resp is None or resp.code != 200:
            self.logger.error("Unable to play the video. Code returned was %s", resp.code if resp is not None else None)
            raise DeviceError("Unable to play video")

        current, duration = -1, 0
        try:
            while duration <= duration:
                interval = show_progress(current, duration)
                if interval == 0:
                    break
                sleep(interval)
                current, duration = self.get_position()
        except KeyboardInterrupt:
            print("\r\nStopping...")

        print('\r\n')
        video_srv.stop()

    def get_position(self):
        data = self.http.simple_request('/scrub')
        if data is None:
            return 0.0, 0.0

        def getfloat(key):
            return float(data.get(key, '0.0'))

        return getfloat(b'position'), getfloat(b'duration')

    def stop(self):
        data = self.http.post_data('/stop')
        if data.code == 200:
            return True
        return False


class Chromecast(object):
    def __init__(self, device=None):
        if device is None:
            return

        self.width = 1920
        self.height = 1080

        self.info = {}
        self.txt = device.get('TXT')
        self.output = (-1, -1)
        self.ptr = device.get('PTR')
        self.host = device.get('A')
        self.host6 = device.get('AAAA')
        srv = device.get('SRV', {})
        self.port = srv.get('port', 8009)
        self.name = srv.get('name')

        self.http = HttpClient(self.host, self.port)
        self.dial = HttpClient(self.host, 8008)
        if self.ptr is not None:
            self.get_info()

        self.client = ChromecastClient(self.host, self.port)

    def __str__(self):
        return "Chromecast: {} @ {}".format(self.name, self.host)

    def get_info(self):
        UPNP_NS = "{urn:schemas-upnp-org:device-1-0}"
        xml = self.dial.simple_request('/ssdp/device-desc.xml')
        if xml is None:
            return

        def get_xpath(_tree, _node, raw=False):
            _xpath = './/' + '/'.join(['*[local-name()="{}"]'.format(p) for p in _node.split('/')])
            matches = _tree.xpath(_xpath)
            if raw:
                return matches
            if len(matches) > 0:
                return matches[0].text
            return ''

        info = {}
        info['URLBase'] = get_xpath(xml, 'URLBase')
        info['api_version'] = "{}.{}".format(get_xpath(xml, 'specVersion/major'),
                                             get_xpath(xml, 'specVersion/minor'))
        info['deviceType'] = get_xpath(xml, 'device/deviceType')
        info['friendlyName'] = get_xpath(xml, 'device/friendlyName')
        info['manufacturer'] = get_xpath(xml, 'device/manufacturer')
        info['modelName'] = get_xpath(xml, 'device/modelName')
        info['UDN'] = get_xpath(xml, 'device/UDN')
        self.info = info

        svcs = []
        for svc in get_xpath(xml, 'serviceList/service', True):
            vals = ('serviceType', 'serviceId', 'controlURL', 'eventSubURL', 'SCPDURL')
            svcs.append({k: get_xpath(svc, k) for k in vals})
        self.services = svcs

    def reboot(self):
        """ Ask the Chromecast to reboot.
        :return: None.
        """
        self.dial.post_data("/setup/reboot", data='{"params": "now"}', ct='application/json')

    def stop(self):
        if self.client.running is True:
            return
        self.client.stop()

    def stop_video(self):
        if self.client.running:
            self.client.stop_apps()
        return True

    def play_video(self, video_srv):
        self.client.start()
        if not self.client.running:
            return

        ck = self.client.get_app_availability(self.client.DEFAULT_MEDIA_APP)
        if not ck.get(self.client.DEFAULT_MEDIA_APP, False):
            return
        self.client.stop_apps()
        sess = self.client.launch_app()
        if sess is None:
            self.logger.warning("Unable to get a media player session.")
            video_srv.stop()
            return

        sess.connect()
        if not sess.connected:
            self.logger.warning("Unable to connect to the media player session.")
            video_srv.stop()
            return
        duration = video_srv.video.info.get('duration')
        ck = sess.load_movie(video_srv.url, video_srv.content_type, duration)
        if ck:
            sess.play_media()

        while not sess.media_finished:
            try:
                sess.get_media_status()
                sleep(0.25)
                if not sess.media_finished:
                    interval = show_progress(sess.media_position, duration)
                    sleep(interval)
            except KeyboardInterrupt:
                print("\nStopping....\n")
                break

        print("Finished.")
        video_srv.stop()
