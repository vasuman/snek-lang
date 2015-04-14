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
        print 'km:', self.kmap
        if not qual in self.kmap:
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

class Context():
    def __init__(self, specs, params):
        self.specs = specs
        self.params = params


class Field():
    def __init__(self, type, id):
        self.type = type
        self.id = id

    def assert_type(self, val):
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
        if type(params) == map:
            if set(params.keys()) != set(self.fmap.keys()):
                raise TypeException("field names don't match")
            for k, v in params.items():
                self.fmap[k].assert_type(v)
            return AttrDict(params)
        elif type(params) == tuple:
            if len(params) != len(self.fmap):
                raise TypeException("param length mismatch")
            a = AttrDict()
            for i, item in enumerate(params):
                f = self.fields[i]
                f.assert_type(item)
                a[f.id] = item
            return a
        else:
            raise TypeException("unhandled params case")

class Empty():
    def validate(self, quals):
        assert_empty(quals)
        return True

    def new(self, specs, params):
        assert_empty(specs)
        if params != None:
            raise TypeException("Empty type takes no `parameters`")
        return None

# FIXME -- check namespace to see if name is free
MAX_RANGE = 500
def get_func_name(ns):
    return '_trap_func%s' % random.randint(1, MAX_RANGE)

GET_REACTOR_FUNC = '_get_reactor'
GET_MODULE_FUNC = '_get_module'

TRAP_PARAMS = []

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
    def __init__(self, name):
        self.name = name
        self.states = {}
        self.state = None
        self.default = None
        self.reactor = None
        self._namespace = {}
        self._setup_namespace()

    def _add_func(self, func):
        self._namespace[func.__name__] = func

    def _setup_namespace(self):
        def match_state(state):
            def wrapper(func):
                def f(*args, **kwargs):
                    if self.state == state:
                        func(*args, **kwargs)
                    else:
                        print 'st mismatch', self.state, state
                return f
            return wrapper

        exec '' in self._namespace
        self._namespace[GET_REACTOR_FUNC] = lambda : self.reactor
        self._namespace[GET_MODULE_FUNC] = lambda : self
        self._add_func(match_state)

    def _exec(self, name):
        def wrapper(*args, **kwargs):
            call_string = '%s(*%s, **%s)' % (name, args, kwargs)
            exec call_string in self._namespace
        return wrapper

    def assemble_trap(self, name, body, state):
        # Parsing body
        bmod = ast.parse(body)
        fmod = ast.parse(FUNC_TEMPLATE % (state, ','.join(TRAP_PARAMS)))
        # Defining function
        func_def = fmod.body[0]
        func_def.name = name
        func_def.body = bmod.body
        # Encapsulating in module
        ast.fix_missing_locations(fmod)
        # Compiling!!
        exec compile(fmod, '<ast>', 'exec') in self._namespace
        return self._exec(name)

class Event():
    def __init__(self, name, qual, params):
        self.name = name
        self.qual = qual
        self.params = params

class SnekFile(object):
    def __init__(self):
        self.modules = []
        self.events = {}
        self.decl = None
