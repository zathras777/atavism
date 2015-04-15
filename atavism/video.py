from errno import EPERM, EACCES
import os
import sys
import subprocess
from tempfile import mkdtemp
import re
import math


def find_ffmpeg(binary_name='ffmpeg', skip_list=None, paths=None, silent=False):
    """ Function to find and return the full path to a suitable ffmpeg binary.
        If no suitable ffmpeg binary is found, a RuntimeError exception is raised.
    :param binary_name: The name of the binary to search for. Default is ffmpeg
    :param skip_list: List of binary files to skip.
    :param paths: Additional system paths to include in search.
    :return: Path to ffmpeg binary.
    """
    found = False
    if skip_list is None:
        skip_list = []
    os_paths = ['/usr/bin', '/usr/local/bin']
    if paths is not None:
        if isinstance(paths, (list, tuple)):
            for p in reversed(paths):
                os_paths.insert(0, p)
        else:
            os_paths.insert(0, paths)
    for p in os_paths:
        poss = os.path.join(p, binary_name)
        if os.path.exists(poss) and os.path.isfile(poss) and poss not in skip_list:
            found = True
            break

    if not found:
        raise RuntimeError("\nNo binary '{}' has been found. Paths tried: {}".
                           format(binary_name, ','.join(os_paths)))

    # Check for hls support
    try:
        p = subprocess.Popen([poss, '-protocols'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
    except (IOError, OSError) as e:
        if e.errno in (EPERM, EACCES):
            if not silent:
                print("\n'{}' is not an executable file.".format(poss))
            found = False

    if not found:
        skip_list.append(poss)
        return find_ffmpeg(binary_name=binary_name, skip_list=skip_list)

    if b'hls' not in out:
        if not silent:
            print("HLS was not found in the protocols list for '{}'.\n"\
                  "Without HLS support we can't use this {}.".format(poss, binary_name))
        skip_list.append(poss)
        return find_ffmpeg(binary_name=binary_name, skip_list=skip_list)

    # Check for libx264
    p = subprocess.Popen([poss, '-encoders'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate()
    if b'libx264' not in out:
        if not silent:
            print("libx264 was not found in the encoders list for '{}'.\n"\
                  "As we require libx264, we can't use this {}.".format(poss, binary_name))
        skip_list.append(poss)
        return find_ffmpeg(binary_name=binary_name, skip_list=skip_list)

    return poss


class BaseVideo(object):
    def __init__(self, source):
        self.source = source
        self.directory = os.path.dirname(source)

    def url(self):
        return "/{}".format(os.path.basename(self.source))

    def find_file(self, url):
        poss_fn = os.path.join(self.directory, url[1:] if url.startswith('/') else url)
        if not os.path.exists(poss_fn):
            return None
        return poss_fn


class SimpleVideo(BaseVideo):
    def __init__(self, source):
        BaseVideo.__init__(self, source)


class HLSVideo(BaseVideo):
    """ We will attempt to create a temporary directory to contain the segments of an HLS
        stream. The files are removed when the instance that created them is deleted.
    """
    def __init__(self, source, tmp_base=None, ffmpeg=None):
        BaseVideo.__init__(self, source)
        self.cleanup = True
        self.fn = os.path.splitext(os.path.basename(source))[0] + '.m3u8'
        self.directory = mkdtemp(dir=tmp_base or '/tmp')
        self.hls_filename = os.path.join(self.directory, self.fn)
        self.ffmpeg = ffmpeg or find_ffmpeg()
        self.streams = []
        self.video_stream = None
        self.meta = {}
        self.duration_data = {}
        self.hls_time = 10
        self.segments = 0

        self.get_video_information()

    def url(self):
        return "/{}".format(self.fn)

    def __del__(self):
        if self.cleanup:
#            print("Removing directory {}".format(self.directory))
            for f in os.listdir(self.directory):
                os.unlink(os.path.join(self.directory, f))
            os.rmdir(self.directory)

    def create_hls(self, max_width=-1, max_height=-1):
        opts = []
        if self.needs_resize(max_width, max_height):
            opts.extend(['-vf', 'scale={}:{}'.format(*self._resized(max_width, max_height))])

        output, err = self._hls_command(opts)
        self.segments = len(os.listdir(self.directory)) - 1
        if self.segments > 0:
            return True
        print(output)
        print(err)

        return False

    def get_video_information(self):
        ignored, data = self._execute_ffmpeg([])
        for input in data.split(b'\nInput')[1:]:
            for l in [ln.strip() for ln in input.split(b'\n')]:
                if not l.startswith(b'Stream'):
                    continue
                info = re.match(b'^Stream #([0-9]\:[0-9])\(?([A-Za-z]{2,})?\)?: ([A-Za-z]+):', l)
                if info is None:
                    continue
                sinfo = {'type': info.group(3), 'n': info.group(1), 'lang': info.group(2)}
                parts = b'.'.join(l.split(b': ')[2:]).split(b', ')

                if info.group(3) == b'Video':
                    if self.video_stream is None:
                        self.video_stream = sinfo
                    for p in parts:
                        if b'fps' in p:
                            sinfo['fps'] = float(p.replace(b'fps', b'').strip())
                        elif re.search(b'[0-9]{2,}x[0-9]{2,}', p):
                            sz = re.search(b'([0-9]{2,})x([0-9]{2,})', p)
                            sinfo['width'] = int(sz.group(1))
                            sinfo['height'] = int(sz.group(2))
                self.streams.append(sinfo)

    def video_width(self):
        if self.video_stream is None:
            return -1.0
        return float(self.video_stream.get('width', -1))

    def video_height(self):
        if self.video_stream is None:
            return -1.0
        return float(self.video_stream.get('height', -1))

    def has_audio(self):
        for s in self.streams:
            if s.get('type') == b'Audio':
                return True
        return False

    def audio_streams(self):
        n = 0
        for s in self.streams:
            if s.get('type') == b'Audio':
                n += 1
        return n

    def needs_resize(self, max_width=-1, max_height=-1):
        if max_width == -1 and max_height == -1:
            return False
        if max_width != -1 and self.video_width() > max_width:
            return True
        if max_height != -1 and self.video_height() > max_height:
            return True
        return False

    def _resized(self, max_width, max_height):
        rw = max_width / self.video_width() if max_width != -1 else 1.0
        rh = max_height / self.video_height() if max_height != -1 else 1.0
        ratio = min(rw, rh)
        w = int(math.floor(self.video_width() * ratio))
        h = int(math.floor(self.video_height() * ratio))
        if w % 2 != 0:
            w -= 1
        if h % 2 != 0:
            h -= 1
        return w, h

    def _execute_ffmpeg(self, *args):
        cmd_args = [self.ffmpeg, '-i', self.source]
        cmd_args.extend(*args)
        p = subprocess.Popen(cmd_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return p.communicate()

    def _hls_command(self, *opts):
        args = ['-hls_time', str(self.hls_time), '-hls_list_size', '0', '-f', 'hls']
        args.extend(*opts)
        args += [self.hls_filename]
        return self._execute_ffmpeg(args)
