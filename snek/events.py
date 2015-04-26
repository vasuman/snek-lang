import sys
import traceback
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


class Context():
    def __init__(self, specs, params, extra):
        self.specs = specs
        self.params = params
        self.extra = extra

class Event():

    def __init__(self, name, typ):
        self.name = name
        self.typ = typ
        self._handlers = []

    def trap(self, quals, handler):
        self.typ.validate(quals)
        self._handlers.append((quals, handler))

    def fire(self, specs, params, extra):
        m = []
        for quals, handler in self._handlers:
            v = matches(specs, quals)
            if v is not None:
                m.append((v, handler))
        ctx = Context(specs, params, extra)
        for _, handler in sorted(m, reverse=True):
            handler(ctx)


class Reactor(threading.Thread):

    def __init__(self):
        super(Reactor, self).__init__()
        self.running = False
        self._eq = Queue()
        self.sp = Queue()
        self._handlers = {}
        self._transitions = []
        self._input_thread = None

    def _get_input(self, prompt, mod):
        if self._input_thread:
            raise Exception('Input thread already running')
        def handle():
            ip = raw_input(prompt)
            self._input_thread = None
            for handler in mod.input_handlers:
                handler(ip)
        self._input_thread = threading.Thread(target=handle)
        self._input_thread.start()
        
    def _do_transition(self, mod, state):
        print '\nTransition %s from %s to %s' % (mod.name, mod.state, state)
        if mod.state and mod.states[mod.state].on_exit:
            mod.states[mod.state].on_exit(state)
        prev_state = mod.state
        mod.state = state
        if mod.state and mod.states[mod.state].on_entry:
            mod.states[state].on_entry(prev_state)

    def special(self, func, args):
        self.sp.put((func, args))
        self._blank()

    def run(self, *args, **kwargs):
        self.running = True
        print 'Reactor started'
        while self.running:
            try:
                while not self.sp.empty():
                    func, args = self.sp.get()
                    func(*args)
                self._transitions = []
                event, specs, params, extra = self._eq.get()
                if event == 0:
                    continue
                event.fire(specs, params, extra)
                for mod, state in self._transitions:
                    self._do_transition(mod, state)
            except Exception as e:
                print 'Reactor caught, '
                print traceback.format_exc()
        print 'Reactor exited'
        sys.exit(0)

    def submit(self, event, specs, params, extra = None):
        self._eq.put((event, specs, event.typ.new(specs, params), extra))

    def transition(self, mod, state):
        self._transitions.append((mod, state))
        self._blank()

    def init(self, mod):
        assert mod.reactor == mod.state == None, 'module already initialized'
        mod.set_reactor(self)
        self._do_transition(mod, mod.default)

    def stop(self):
        self.running = False
        self._blank()

    def _blank(self):
        self._eq.put((0, None, None, None))
