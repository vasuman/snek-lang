import threading
from Queue import Queue

LOCAL = 0b01
REMOTE = 0b10
ANY = 0b11


def matches(specs, quals):
    l = len(quals)
    if not specs[:l] == quals:
        return
    return l


class Event():

    def __init__(self, name, typ):
        self.name = name
        self.typ = typ
        self._handlers = []

    def trap(self, quals, handler):
        # TODO(vasuman): Check `quals`
        self.typ.validate(quals)
        self._handlers.append((quals, handler))

    def fire(self, specs, params):
        m = []
        p = self.typ.new(specs, params)
        for quals, handler in self._handlers:
            v = matches(specs, quals)
            if v is not None:
                m.append((v, handler))
        print m
        for _, handler in sorted(m, reverse=True):
            handler(params)


class Reactor(threading.Thread):

    def __init__(self):
        super(Reactor, self).__init__()
        self.running = False
        self.eq = Queue()
        self._handlers = {}
        self._transitions = []

    def _do_transition(self, mod, state):
        if mod.state and mod.states[mod.state].on_exit:
            mod.states[mod.state].on_exit()
        mod.state = state
        if mod.state and mod.states[mod.state].on_entry:
            mod.states[state].on_entry()

    def run(self, *args, **kwargs):
        self.running = True
        while self.running:
            for mod, state in self._transitions:
                self._do_transition(mod, state)
            event, specs, params = self.eq.get()
            event.fire(specs, params)

    def submit(self, event, specs, params=None):
        self.q.put((event, specs, params))

    def transition(self, mod, state):
        self._transitions.append((mod, state))

    def init(self, mod):
        assert mod.reactor == mod.state == None, 'module already initialized'
        mod.reactor = self
        self._do_transition(mod, mod.default)
