import json
import socket as sck
import threading
import base64

def serialize(specs, params):
    x = {}
    x['specs'] = specs
    x['params'] = params
    return base64.b64encode(json.dumps(x))

def deserialize(dat):
    s = base64.b64decode(dat)
    j = json.loads(s)
    return j['specs'], j['params']

class EventDispatcher(object):

    def __init__(self):
        self.on = {}

    def set_reactor(self, reactor):
        self.reactor = reactor

    def _dispatch_handlers(self, event, *args):
        if event not in self.on:
            return
        for handler in self.on[event]:
            self.reactor.special(handler, args)

    def add_listener(self, event, listener):
        if event not in self.on:
            self.on[event] = []
        self.on[event].append(listener)

BUF_SIZE = 1024
DELIM = '\n'
EVENTS = ['connected', 'disconnected']
class Pipe(EventDispatcher):

    def __init__(self, name, event, sock = None, remote = None):
        super(Pipe, self).__init__()
        self.name = name
        self.event = event
        if sock is None:
            self._sock = sck.socket(sck.AF_INET, sck.SOCK_STREAM)
        else:
            self._sock = sock
        self.remote = remote
        self._thread = None
        self.buf = ''

    def _extra(self):
        ret = {}
        if self.remote is not None:
            ret['remote'] = self.remote
        ret['comm'] = self
        return ret

    def _do_listen(self):
        while True:
            data = self._sock.recv(BUF_SIZE)
            if not data:
                self._dispatch_handlers('disconnected', self, None)
                return
            if data[-1] == DELIM:
                specs, params = deserialize(self.buf + data[:-1])
                self.reactor.submit(self.event, specs, params, extra = self._extra())
                self.buf = ''
            else:
                self.buf += data

    def _init_thread(self):
        self._thread = threading.Thread(target = self._do_listen)
        self._thread.start()

    def connect(self, remote_addr):
        self._sock.connect(remote_addr)
        self._dispatch_handlers('connected', self, None)
        self._init_thread()

    def pump(self, event, spec, params):
        if event != self.event:
            raise Exception('event type mismatch!')
        self._sock.send(serialize(spec, params))
        self._sock.send(DELIM)

def to_pair(remote):
    return '%s:%d' % remote

LOCALHOST = '127.0.0.1'
class Port(EventDispatcher):

    def __init__(self, name, event):
        super(Port, self).__init__()
        self.name = name
        self.event = event
        self.pipes = {}
        self._thread = None
        self.cnt = 0

    def listen(self, port):
        self._sock = sck.socket(sck.AF_INET, sck.SOCK_STREAM)
        self._sock.bind((LOCALHOST, port))
        self._sock.listen(5)
        self._thread = threading.Thread(target=self._do_accept)
        self._thread.start()

    def _pipe_disconnected(self, remote):
        def handler(pipe):
            del self.pipes[remote]
            self._dispatch_handlers('disconnected', self, remote)
        return handler

    def pump(self, event, spec, params):
        for pipe in self.pipes.values():
            pipe.pump(event, spec, params)

    def _do_accept(self):
        while True:
            sock, remote = self._sock.accept()
            pipe_name = '%s#%s' % (self.name, self.cnt)
            self.cnt += 1
            pipe = Pipe(pipe_name, self.event, sock, remote)
            pipe.set_reactor(self.reactor)
            self.pipes[remote] = pipe
            #TODO(vasuman): fire connected event
            self._dispatch_handlers('connected', self, remote)
            pipe.add_listener('disconnected', self._pipe_disconnected(remote))
            pipe._init_thread()
