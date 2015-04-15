import socket as sck
import threading
import base64

def serailize(specs, params):
    x = {}
    x['specs'] = specs
    x['params'] = params
    return base64.b64encode(json.dumps(x))

def deserialize(dat):
    s = base64.b64decode(dat)
    j = json.loads(s)
    return j['specs'], j['params']

class EventDispatcher():

    def __init__(self, reactor):
        self.on = {}

    def _dispatch_handlers(self, event, *args):
        if event not in self.on:
            return
        for handler in self.on[event]:
            reactor.special(handler, args)

    def add_listener(self, event, listener):
        if event not in self.on:
            self.on[event] = []
        self.on[event].append(listener)

BUF_SIZE = 1024
DELIM = '\n'
EVENTS = ['connected', 'disconnected']
class Pipe(EventDispatcher):

    def __init__(self, name, event, reactor, sock = None):
        super(Pipe, self).__init__(reactor)
        self.name = name
        self.event = event
        if sock is None:
            self._sock = sck.socket(sck.AF_INET, sck.SOCK_STREAM)
        else:
            self._sock = sock
        self.reactor = reactor
        self._thread = None
        self.buf = ''

    def _do_listen(self):
        while True:
            data = socket.recv(BUF_SIZE)
            if not data:
                self._dispatch_handlers('disconnected', (self,))
                return
            if data[-1] == DELIM:
                specs, params = deserialize(self.buf + data)
                self.reactor.submit(self.event, specs, params)
                self.buf = ''
            else:
                self.buf += data

    def _init_thread(self):
        self._thread = threading.Thread(target = self._do_listen)

    def connect(self, remote_addr):
        self._sock.connect(remote_addr)
        self._dispatch_handlers('connected', (self,))
        self._init_thread()

    def pump(self, spec, params):
        self._sock.send(serialize(spec, params))
        self._sock.send('\n')

def to_pair(remote):
    return '%s:%d' % remote

LOCALHOST = '127.0.0.1'
class Port(EventDispatcher):

    def __init__(self, name, event, reactor):
        super(Port, self).__init__(reactor)
        self.name = name
        self.event = event
        self.pipes = {}
        self.reactor = reactor
        self._thread = None
        self.cnt = 0

    def listen(self, port):
        self._sock = sck.socket(sck.AF_INET, sck.SOCK_STREAM)
        self._sock.bind((LOCALHOST, port))
        self._sock.listen(5)
        self._thread = threading.Thread(target=_do_accept)

    def _pipe_disconnected(self, remote):
        def handler(pipe):
            del self.pipes[remote]
            self._dispatch_handlers('disconnected', (self, remote, pipe))
        return handler

    def _do_accept(self):
        while True:
            sock, remote = self._sock.accept()
            pipe_name = '%s#%s' % (self.name, self.cnt)
            self.cnt += 1
            pipe = Pipe(pipe_name, self.event, self.reactor, sock)
            self.pipes[remote] = pipe
            #TODO(vasuman): fire connected event
            self._dispatch_handlers('connected', (self, remote, pipe))
            pipe.add_listener('disconnected', self._pipe_disconnected(remote))
            pipe._init_thread()
