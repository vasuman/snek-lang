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
        self.sp = Queue()
        self._handlers = {}
        self._transitions = []

    def _do_transition(self, mod, state):
        print 'Transition %s from %s to %s' % (mod.name, mod.state, state)
        if mod.state and mod.states[mod.state].on_exit:
            mod.states[mod.state].on_exit(state)
        prev_state = mod.state
        mod.state = state
        if mod.state and mod.states[mod.state].on_entry:
            mod.states[state].on_entry(prev_state)

    def special(self, func, *args):
        self.sp.put((func, args))

    def run(self, *args, **kwargs):
        self.running = True
        print 'Reactor started'
        while self.running:
            try:
                while not self.sp.empty():
                    func, args = self.sp.get()
                    func(*args)
                for mod, state in self._transitions:
                    self._do_transition(mod, state)
                event, specs, params = self.eq.get()
                event.fire(specs, params)
            except e:
                print 'Reactor caught, ', e
        print 'Reactor exited'

    def submit(self, event, specs, params=None):
        self.eq.put((event, specs, params))

    def transition(self, mod, state):
        self._transitions.append((mod, state))

    def init(self, mod):
        assert mod.reactor == mod.state == None, 'module already initialized'
        mod.reactor = self
        self._do_transition(mod, mod.default)
