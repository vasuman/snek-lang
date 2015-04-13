import ast
import _ast
import events

def match(*args):
    def dec(func):
        def wrap(ctx, event):
            x = event
            for arg in args:
                if not arg in x:
                    return
                x = x[arg]
            func(x)
    return wrap

class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super(self, AttrDict).__init__(self, *args, **kwargs)

    def __getattr__(self, attr):
        return self.__getitem__(attr)

    def __setattr__(self, attr, val):
        return self.__setitem__(attr, val)

class TypeException(Exception):
    pass

class UnionValidator():
    def __init__(self, kmap):
        self.kmap = kmap

    def new(self, *args):
        if len(args) == 0:
            return Sentinal()
        qual = args[0]
        if not qual in self.kmap:
            raise TypeException("invalid qual %s" % qual)
        return self.kmap[qual].new(*args[1:])

class StructField():
    def __init__(self, type, id):
        self.type = type
        self.id = id

    def assert_type(self, val):
        if type(val) != self.type:
            raise TypeException("type for field %s don't match" % self.id)


class StructValidator():
    def __init__(self, fields):
        self.fmap = {f.id: f for f in fields}
        self.fields = fields

    def new(self, params):
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

class Sentinal():
    pass

class EmptyValidator():
    def new(self):
        return Sentinal()

MAX_RANGE = 500
def get_func_name():
    return '_trap_func%s' % random.randint(1, MAX_RANGE)

def assemble_func(body, name, params, ns):
    # Parsing body
    bmod = ast.parse(body)
    # Generating arguments
    nargs = [ast.Name(param, ast.Param()) for param in params]
    args = _ast.arguments(nargs, None, None, [])
    # Defining function
    func_def = ast.FunctionDef(name, args, bmod.body, [])
    # Encapsulating in module
    mod = ast.Module([func_def])
    ast.fix_missing_locations(mod)
    # Compiling!!
    exec compile(mod, '<ast>', 'exec') in ns

class StateTrap():
    def __init__(self, event_name, quals, func_name):
        self.event_name = event_name
        self.quals = quals
        self.func_name = func_name

class ModuleState():
    def __init__(self, name):
        self.name = name
        self.traps = []

    def capture(self, event):
        for trap in self.traps:
            if trap.satisfies(event):
                yield trap.func_name

GET_REACTOR_FUNC = '_get_reactor'
GET_MODULE_FUNC = '_get_module'

class SnekModule():
    def __init__(self, name):
        self.name = name
        self.states = {}
        self._current = None
        self._namespace = {}
        self._reactor = events.EventReactor()

    def _setup_namespace(self):
        exec '' in self._namespace
        self._namespace['_get_reactor'] = lambda : self._reactor
        self._namespace['_get_module'] = lambda : self

    def _dispatch_event(self, event):
        pass

class Event():
    def __init__(self, name, qual, params):
        self.name = name
        self.qual = qual
        self.params = params
        
class SnekFile(object):
    def __init__(self):
        self.modules = {}
        self.events = {}
        self.decl = None
