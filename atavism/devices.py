from time import sleep
import re
import math
from atavism.http11.client import HttpClient


class AirplayDeviceError(Exception):
    pass


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
            raise AirplayDeviceError("Unable to get device information as no IPv4 or IPv6 address available?")

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

        pdata = {'Content-Location': video_srv.url(), 'Start-Position': 0}
        resp = self.http.post_data('/play', pdata, 'text/parameters')
        if resp is None or resp.code != 200:
            raise AirplayDeviceError("Unable to play the video.")

        # need to pause to allow things to settle...
        try:
            sleep(self.UPDATE_INTERVAL)
            current, duration = self.get_position()
            while duration > 0 and current < duration:
                try:
                    current, duration = self.get_position()
                    interval = self.UPDATE_INTERVAL
                    if current > 0:
                        n = (current / duration) * 100
                        bar = "#" * int(math.floor(n / 2.0))
                        interval = 2
                    elif current == 0 and duration == 0:
                        bar = ' Completed'
                        n = 100.0
                    else:
                        bar = ' Buffering...'
                        n = 0.0
                    print('\r   Playback: [%-50s] %.03f%%' % (bar, n))
                    sleep(interval)
                except KeyboardInterrupt:
                    print("\r\nStopping...")
                    break
            print('\r\n')
            sleep(2)
        except KeyboardInterrupt:
            print("  Stopping....")
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
