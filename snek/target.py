import ast
import _ast
import events
import random


class AttrDict(dict):

    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)

    def __getattr__(self, attr):
        return self.__getitem__(attr)

    def __setattr__(self, attr, val):
        return self.__setitem__(attr, val)


class TypeException(Exception):
    pass


class Union():

    def __init__(self, kmap):
        self.kmap = kmap

    def assert_has(self, qual):
        if qual not in self.kmap:
            raise TypeException("invalid specifier %s" % qual)

    def new(self, specs, params):
        if len(specs) == 0:
            raise TypeException("not enough `specifiers`")
        self.assert_has(specs[0])
        return self.kmap[specs[0]].new(specs[1:], params)

    def validate(self, quals):
        if len(quals) == 0:
            return True
        self.assert_has(quals[0])
        return self.kmap[quals[0]].validate(quals[1:])

class Field():

    def __init__(self, type, id):
        self.type = type
        self.id = id

    def assert_type(self, val):
        if self.type == str and type(val) == unicode:
            return
        if type(val) != self.type:
            raise TypeException("type for field %s don't match" % self.id)


def assert_empty(ls):
    if len(ls) != 0:
        raise TypeException("dangling, %s" % ls)


class Struct():

    def __init__(self, fields):
        self.fmap = {f.id: f for f in fields}
        self.fields = fields

    def validate(self, quals):
        assert_empty(quals)
        return True

    def new(self, specs, params):
        assert_empty(specs)
        if type(params) == dict:
            if set(params.keys()) != set(self.fmap.keys()):
                raise TypeException("field names don't match")
            for k, v in params.items():
                self.fmap[k].assert_type(v)
            return AttrDict(params)
        elif type(params) in (tuple, list):
            if len(params) != len(self.fmap):
                raise TypeException("param length mismatch")
            a = AttrDict()
            for i, item in enumerate(params):
                f = self.fields[i]
                f.assert_type(item)
                a[f.id] = item
            return a
        else:
            raise TypeException("unhandled params case ", params, type(params))


class Empty():

    def validate(self, quals):
        assert_empty(quals)
        return True

    def new(self, specs, params):
        assert_empty(specs)
        if params is not None:
            raise TypeException("Empty type takes no `parameters`")
        return None

# FIXME -- check namespace to see if name is free
MAX_RANGE = 500


def get_func_name(ns):
    return '_trap_func%s' % random.randint(1, MAX_RANGE)

GET_REACTOR_FUNC = '_get_reactor'
GET_MODULE_FUNC = '_get_module'
GET_EVENT_FUNC = '_get_event'

FUNC_TEMPLATE = '''
@match_state("%s")
def f(%s):
  pass
'''


class ModState():

    def __init__(self, name):
        self.name = name
        self.on_entry = None
        self.on_exit = None


class SnekModule():

    def __init__(self, name, f):
        self.name = name
        self.f = f
        self.gs = []
        self.comms = {}
        self.states = {}
        self.state = None
        self.default = None
        self.reactor = None
        self._namespace = {}
        self._setup_namespace()
        self.input_handlers = []

    def set_reactor(self, reactor):
        self.reactor = reactor
        for comm in self.comms.values():
            comm.set_reactor(reactor)

    def _add_func(self, func):
        self._namespace[func.__name__] = func

    def _setup_namespace(self):
        def match_state(state):
            def wrapper(func):
                def f(*args, **kwargs):
                    if self.state == state:
                        func(*args, **kwargs)
                return f
            return wrapper

        exec '' in self._namespace
        self._namespace[GET_REACTOR_FUNC] = lambda: self.reactor
        self._namespace[GET_MODULE_FUNC] = lambda: self
        self._namespace[GET_EVENT_FUNC] = lambda name: self.f.events[name]
        self._add_func(match_state)

    def init_globals(self, block):
        body = ast.parse(block).body
        for stmt in body:
            if type(stmt) != ast.Assign:
                raise TypeException('not an assign statement')
            targets = stmt.targets
            if len(targets) != 1:
                raise TypeException('multipe assignments not allowed')
            self.gs.append(targets[0].id)
        exec block in self._namespace

    def _wrap_exec(self, fname):
        def wrapper(*args, **kwargs):
            #TODO: check if name not used in namespace
            names = []
            for i, arg in enumerate(args):
                name = '_arg%d' % i
                self._namespace[name] = arg
                names.append(name)
            for i, key, kwarg in enumerate(kwargs):
                name = '_kwarg%d' % i
                self._namespace[name] = kwarg
                names.append('%s = %s' % (key, name))
            call_string = '%s(%s)' % (fname, ', '.join(names))
            exec call_string in self._namespace
        return wrapper

    def assemble_trap(self, name, body, state, params=[]):
        globals_str = 'globals %s' % ','.join(self.gs + self.comms.keys())
        # Parsing body
        bmod = ast.parse(body)
        fmod = ast.parse(FUNC_TEMPLATE % (state, ','.join(params)))
        # Defining function
        func_def = fmod.body[0]
        func_def.name = name
        func_def.body = bmod.body
        # Encapsulating in module
        ast.fix_missing_locations(fmod)
        # Compiling!!
        exec compile(fmod, '<ast>', 'exec') in self._namespace
        return self._wrap_exec(name)

    def add_comm(self, comm):
        self.comms[comm.name] = comm
        self._namespace[comm.name] = comm

    def exec_decl(self, decl):
        exec decl in self._namespace

class SnekFile(object):

    def __init__(self):
        self.modules = []
        self.events = {}
        self.decl = None

    def get_module(self, name):
        for module in self.modules:
            if module.name == name:
                return module
        return None

    def done_parse(self):
        if self.decl is not None:
            for module in self.modules:
                module.exec_decl(self.decl)
