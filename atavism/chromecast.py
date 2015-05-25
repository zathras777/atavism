import json
import logging
from random import randint
from select import select
from struct import pack, unpack, unpack_from
import socket
import ssl
from threading import Thread, Event

try:
    from queue import Queue, Empty
except ImportError:
    from Queue import Queue, Empty


CONNECTION_NS = "urn:x-cast:com.google.cast.tp.connection"
HEARTBEAT_NS = 'urn:x-cast:com.google.cast.tp.heartbeat'
RECEIVER_NS = 'urn:x-cast:com.google.cast.receiver'
AUTH_NS = 'urn:x-cast:com.google.cast.tp.deviceauth'
MEDIA_NS = 'urn:x-cast:com.google.cast.media'

PLATFORM_DEST = 'receiver-0'


class ProtoBuff(object):
    PROTOCOL_VERSION = 0
    TYPE_ENUM = 0
    TYPE_STRING = 2
    TYPE_BYTES = TYPE_STRING
    TYPE_NAMES = { 0: 'String', 1: 'Binary' }

    def __init__(self, **kwargs):
        self.protocol = kwargs.get('protocol', self.PROTOCOL_VERSION)
        self.source_id = kwargs.get('source_id', 'source-0')
        self.destination_id = kwargs.get('destination_id', PLATFORM_DEST)
        self.namespace = kwargs.get('namespace', CONNECTION_NS)
        self.type = kwargs.get('type', 0)
        self.data = kwargs.get('data', '')
        if 'json' in kwargs:
            self.from_json(kwargs['json'])
        if 'msg' in kwargs:
            self.from_string(kwargs['msg'], kwargs.get('msg_len', len(kwargs['msg'])))

    @staticmethod
    def _pack_type(field_id, t):
        return (field_id << 3) | t

    @staticmethod
    def _unpack_type(val):
        return val >> 3, val & 0x7

    @staticmethod
    def _data_length(s):
        x = b""
        l = len(s)
        while (l > 0x7F):
            x += pack("B", l & 0x7F | 0x80)
            l >>= 7
        x += pack("B", l & 0x7F)
        return x

    @staticmethod
    def _unpack_varint(bytes):
        """ Convert a varint to an integer.
        :param bytes: Bytes containing the varint.
        :return: integer
        """
        value = 0
        base = 1
        rd = 0
        for raw_byte in bytes:
            val_byte = ord(raw_byte) if type(raw_byte) != int else raw_byte
            rd += 1
            value += (val_byte & 0x7f) * base
            if (val_byte & 0x80):
                # The MSB was set; increase the base and iterate again, continuing
                # to calculate the value.
                base *= 128
            else:
                break
        return value, rd

    def _pack_string(self, n, the_str):
        sl = len(the_str)
        return pack(">BB%ds" % sl, self._pack_type(n, self.TYPE_STRING), sl, the_str.encode())

    @staticmethod
    def _unpack_string(buff):
        slen = unpack_from(">B", buff, 0)[0]
        ss = unpack(">%ds" % slen, buff[1:1+slen])[0]
        return ss, slen + 1

    def as_string(self):
        _msg = pack(">BB", self._pack_type(1, self.TYPE_ENUM), self.PROTOCOL_VERSION)
        _msg += self._pack_string(2, self.source_id)
        _msg += self._pack_string(3, self.destination_id)
        _msg += self._pack_string(4, self.namespace)
        _msg += pack(">BB", self._pack_type(5, self.TYPE_ENUM), self.type)
        _msg += pack(">B", self._pack_type(6, self.TYPE_BYTES))
        _msg_len = self._data_length(self.data)
        _msg += pack(">%ds" % len(_msg_len), _msg_len)
        _msg += pack(">%ds" % len(self.data), self.data.encode())
        return pack(">I%ds" % (len(_msg)), len(_msg), _msg)

    def from_string(self, bytes, blen):
        pos = 0
        while pos < blen:
            a = unpack_from(">B", bytes, pos)[0]
            n, ct = self._unpack_type(a)
            pos += 1
            if n == 1:
                self.protocol = unpack_from(">B", bytes, pos)[0]
                pos += 1
            elif n == 2:
                self.source_id, rd = self._unpack_string(bytes[pos:])
                pos += rd
            elif n == 3:
                self.destination_id, rd = self._unpack_string(bytes[pos:])
                pos += rd
            elif n == 4:
                self.namespace, rd = self._unpack_string(bytes[pos:])
                pos += rd
            elif n == 5:
                self.type = unpack_from(">B", bytes, pos)[0]
                pos += 1
            elif n == 6: # utf-8 payload
                slen, rd = self._unpack_varint(bytes[pos:])
                pos += rd
                self.data = unpack(">%ds" % slen, bytes[pos:pos + slen])[0]
                pos += slen
            elif n == 7: # binary payload
                slen, rd = self._unpack_varint(bytes[pos:])
                pos += rd
                self.data = unpack_from(">%dB" % slen, bytes, pos)[0]
                pos += slen
            else:
                print("n = {}".format(n))
                break

    def as_json(self):
        if self.type == 0:
            return json.loads(self.data.decode())

    def from_json(self, json_data):
        self.data = json.dumps(json_data)

    def dump(self):
        """ Dump info to stdout... """
        print("  Protocol Version:   {}".format(self.protocol))
        print("  Source ID:          {}".format(self.source_id))
        print("  Desination ID:      {}".format(self.destination_id))
        print("  Namespace:          {}".format(self.namespace))
        print("  Type:               {} [{}]".format(self.TYPE_NAMES[self.type], self.type))
        print("  Data:               {}".format(self.data))


class ChromecastClient(object):
    """ Class to communicate with a Chromecast device.

        In order to communicate a virtual connection is required, estblished by using the connect() function.

        Once established the Chromecast will send a PING request, which must be answered with a PONG reply
        or the connection will be closed.


        Useful links:

         - https://developers.google.com/cast/docs/reference/messages

    """
    DEFAULT_MEDIA_APP = 'CC1AD845'

    def __init__(self, host, port=8009):
        self.logger = logging.getLogger()
        self.req_id = None
        self.volume = 0
        self.muted = False
        self.stadby = True
        self.active = False
        self.host = host
        self.port = port

        self.sessions = {}
        self.sessions_updated = Event()
        self.available_apps = set()
        self.apps_available = Event()

        self.connected = False
        self.socket = None

        self.input = Queue()
        self.output = Queue()

        self.running = False

        self.comm_thread = None
        self.switch_thread = None

        self.heartbeat = HeartbeatReceiver(self)

        self.responses = {}
        self.events = {}

    def start(self):
        if self.running is True:
            return

        self.socket = ssl.wrap_socket(socket.socket())
        self.socket.settimeout(10)
        try:
            self.socket.connect((str(self.host), self.port))
        except socket.gaierror as e:
            self.logger.warning("Unable to connect to device. %s", e)
            return

        self.running = True
        self.switch_thread = Thread(target=self.switchboard)
        self.switch_thread.daemon = True
        self.switch_thread.start()

        self.comm_thread = Thread(target=self.communicator)
        self.comm_thread.daemon = True
        self.comm_thread.start()

        self.connect()
        self.get_app_availability(self.DEFAULT_MEDIA_APP)

    def stop(self):
        self.running = False

    def register_event(self, request_id):
        ev = Event()
        self.events[request_id] = ev
        return ev

    def unregister_event(self, request_id):
        if request_id not in self.events:
            return
        del self.events[request_id]

    def communicator(self):
        _buffer = b''
        while self.running:
            w = [self.socket] if self.output.not_empty else []
            _r, _w, _e = select([self.socket], w, [self.socket], 10)

            if len(_e):
                break

            if len(_r) > 0:
                _buffer += self.socket.recv(2048)

            if len(_w) > 0:
                try:
                    pb = self.output.get_nowait()
#                   if pb.namespace != HEARTBEAT_NS:
#                       print(">>>>>>>>>>>>>>")
#                       pb.dump()
                    wl = self.socket.write(pb.as_string())
                    self.output.task_done()
                except Empty:
                    pass

            if len(_buffer) >= 4:
                plen = unpack(">I", _buffer[:4])[0]
                if len(_buffer) >= plen + 4:
                    self.accept_message(_buffer[4:4 + plen], plen)
                    _buffer = _buffer[4 + plen:]

    def switchboard(self):
        while self.running:
            pb = self.input.get()
            self.input.task_done()

            if pb.namespace == HEARTBEAT_NS:
                self.heartbeat.process_message(pb)
                continue

#            print("<<<<<<<<<<<<<<")
#            pb.dump()

            msg = pb.as_json()
            if pb.namespace == CONNECTION_NS:
                if msg.get('type') == 'CLOSE':
                    if pb.source_id in self.sessions:
                        self.sessions[pb.source_id].connected = False
                    continue
            if pb.namespace == MEDIA_NS and pb.destination_id == '*':
                sess = self.sessions.get(pb.source_id)
                if sess is not None:
                    sess.update_media_status(pb.as_json())

            if msg.get('requestId') in self.events:
                self.responses[msg['requestId']] = pb
                self.events[msg['requestId']].set()

    def put_and_wait(self, pb, payload, timeout=10):
        req_id = self.request_id
        payload['requestId'] = req_id
        ev = self.register_event(req_id)
        pb.from_json(payload)
        self.output.put(pb)
        rv = ev.wait(timeout)
        self.unregister_event(req_id)
        if rv and req_id in self.responses:
            rv = self.responses[req_id]
            del self.responses[req_id]
        return rv

    def accept_message(self, bytes, blen):
        pb = ProtoBuff(msg=bytes, msg_len=blen)
        self.input.put(pb)

    @property
    def request_id(self):
        if self.req_id is None:
            self.req_id = randint(1000000, 80000000)
        self.req_id += 1
        return self.req_id

    def stop_apps(self):
        for sess in self.sessions.values():
            self.put_and_wait(ProtoBuff(namespace=RECEIVER_NS), {'type': 'STOP', 'sessionId': sess.session_id})
            sess.disconnect()
            del self.sessions[sess.session_id]

    def connect(self):
        self.output.put(ProtoBuff(data="{\"type\":\"CONNECT\"}"))

    def get_status(self):
        self.put_and_wait(ProtoBuff(namespace=RECEIVER_NS), {'type': 'GET_STATUS'})

    def get_app_availability(self, *apps):
        """ Enquire whether one or more apps are available on the Chromecast.
            We use the cached list wherever possible and block until we have an
            answer.
        :param apps: One or more app names or ids to search for.
        :return: Dict with each app requested as a True/False.
        """
        if len(apps) == 0:
            return
        toask = [a for a in apps if a not in self.available_apps]
        if len(toask) > 0:
            payload = {'type': 'GET_APP_AVAILABILITY',
                       'appId': toask}
            resp = self.put_and_wait(ProtoBuff(namespace=RECEIVER_NS), payload)
            if resp is not False:
                data = resp.as_json()
                for app in data.get('availability', []):
                    if data['availability'][app] == 'APP_AVAILABLE':
                        self.available_apps.add(app)
        return {a: a in self.available_apps for a in apps}

    def launch_app(self, app_id=None, block=True):
        payload = {'type': 'LAUNCH',
                   'appId': app_id or self.DEFAULT_MEDIA_APP}
        resp = self.put_and_wait(ProtoBuff(namespace=RECEIVER_NS), payload)
        if resp is False:
            return None
        app_data = resp.as_json().get('status').get('applications')[0]
        if 'transportId' not in app_data:
            print("The app has been loaded but does not use the cast API.")
            return None
        sess = ChromecastSession(self, app_data)
        self.sessions[app_data['transportId']] = sess
        return sess

    def update_status(self, pb):
        msg = pb.as_json()
        self.volume = msg['status']['volume']['level']
        self.muted = msg['status']['volume']['muted']
        self.standby = msg['status']['isStandBy']
        self.active = msg['status'].get('isActiveInput', False)

        if 'applications' in msg['status']:
            for app in msg['status']['applications']:
                if app['sessionId'] not in self.sessions:
                    self.sessions[app['sessionId']] = ChromecastSession(self, app)
                else:
                    self.sessions[app['sessionId']].update(app)
                self.sessions_updated.set()


class ChromecastSession(object):
    """ Class to contain details of a session on a Chromecast.
    """
    def __init__(self, client, data):
        self.client = client
        self.app_id = data['appId']
        self.display_name = data['displayName']
        self.namespaces = [ns['name'] for ns in data.get('namespaces', [])]
        self.session_id = data['sessionId']
        self.status = data['statusText']
        self.transport_id = data.get('transportId', None)
        self.connected = False

        self.media_loaded = False
        self.media_position = 0
        self.media_status = ''
        self.media_session_id = 0
        self.media_finished = False

    @property
    def uses_cast_api(self):
        return self.transport_id is not None

    def connect(self):
        if self.transport_id is None:
            return
        self.client.output.put(ProtoBuff(namespace=CONNECTION_NS, destination_id=self.transport_id, json={'type': 'CONNECT'}))
        ck = self.client.put_and_wait(ProtoBuff(namespace=MEDIA_NS, destination_id=self.transport_id),
                                                            {'type': 'GET_STATUS'})
        self.connected = ck is not False

    def disconnect(self):
        if not self.connected:
            return
        self.client.output.put(ProtoBuff(namespace=CONNECTION_NS, destination_id=self.transport_id, json={'type': 'CLOSE'}))

    def get_media_status(self):
        if not self.connected or not self.media_loaded:
            return
        update = self.client.put_and_wait(ProtoBuff(namespace=MEDIA_NS, destination_id=self.transport_id), {'type': 'GET_STATUS'})
        if update is not False:
            self.update_media_status(update.as_json())

    def update_media_status(self, data):
        """ This can be called from the parent (if the update was broadcast) or from get_media_status().
        :param data: The update data.
        """
        if data.get('type') != 'MEDIA_STATUS':
            return
        status = data.get('status', {})
        if isinstance(status, list):
            if len(status) == 0:
                return
            status = status[0]
        self.media_session_id = status.get('mediaSessionId')
        self.media_status = status.get('playerState')
        self.media_position = status.get('currentTime')
        if 'idleReason' in status:
            self.media_finished = True

    def get_status(self):
        update = self.client.put_and_wait(ProtoBuff(namespace=self.namespaces[0], destination_id=elf.transport_id),
                                 {'type': 'GET_STATUS', 'mediaSessionId': self.session_id})
        print(update.as_json())

    def load_movie(self, url, ct, duration=None):
        if not self.connected:
            return
        payload = {'type': 'LOAD',
                   'media': {'contentId': url, 'contentType': ct, 'streamType': 'BUFFERING'},
                   'autoplay': False
                   }
        if duration is not None:
            payload['media']['duration'] = duration
        resp = self.client.put_and_wait(ProtoBuff(namespace=self.namespaces[0],
                                                   destination_id=self.transport_id), payload, 15)
        if resp is False:
            print("Chromecast is unable to load media?")
            self.media_loaded = False
            return False
        self.media_loaded = True
        self.get_media_status()
        return True

    def play_media(self):
        if not self.media_loaded:
            return
        payload = {'type': 'PLAY', 'mediaSessionId': self.media_session_id}
        resp = self.client.put_and_wait(ProtoBuff(namespace=self.namespaces[0],
                                                  destination_id=self.transport_id), payload)
        return resp is not False


class ChromecastReceiver(object):
    def __init__(self, client, **kwargs):
        self.client = client
        self.namespace = kwargs.get('namespace')
        self.source = kwargs.get('source_id')
        self.dest = kwargs.get('destination_id')
        self.namespace = kwargs.get('namespace')

    def update_from_message(self, pb):
        if self.source is None:
            self.source = pb.source_id
        if self.dest is None:
            self.dest = pb.destination_id
        if self.namespace is None:
            self.namespace = pb.namespace

    def process_message(self, pb):
        self.update_from_message(pb)
        msg = pb.as_json()


class HeartbeatReceiver(ChromecastReceiver):
    def __init__(self, client, **kwargs):
        ChromecastReceiver.__init__(self, client, **kwargs)

    def process_message(self, pb):
        self.update_from_message(pb)

        msg = pb.as_json()
        if 'type' in msg and msg['type'] == 'PING':
            self.client.output.put(ProtoBuff(source_id=self.source,
                                             destination_id=self.dest,
                                             namespace=self.namespace,
                                             json={'type': 'PONG'}))
