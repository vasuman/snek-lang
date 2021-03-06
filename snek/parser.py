import sys
import tokenize as tkn
from io import BytesIO
import ast
# TODO(vasuman): Package-based relative imports
import target
import events
import net

class ParseException(Exception):
    pass


class Token(object):

    def __init__(self, t):
        self.kind = t[0]
        self.val = t[1]
        self._t = t

    def get_tuple(self):
        return (self.kind, self.val)

    def __str__(self):
        return '%s: %s @ %s' % (tkn.tok_name[self.kind], repr(self.val), self.get_pos())

    def get_pos(self):
        if len(self._t) < 3:
            return '*'
        return repr(self._t[2])

    def __eq__(self, other):
        if self.kind != other.kind:
            return False
        if self.val != other.val:
            return False
        return True

SKIP_TOKENS = [tkn.NL, tkn.COMMENT]


class TokenGen(object):

    def __init__(self, gen):
        self._gen = gen
        self.empty = False
        self._do_peek()

    def __iter__(self):
        return self

    def _do_peek(self):
        try:
            self.peek = Token(self._gen.next())
        except StopIteration:
            self.empty = True
            self.peek = None
            return
        if self.peek.kind in SKIP_TOKENS:
            self._do_peek()
        if self.peek.kind == tkn.ENDMARKER:
            self.empty = True

    def next(self):
        if self.empty:
            raise StopIteration()
        ret_val = self.peek
        self._do_peek()
        return ret_val

    def assert_tok(self, tok):
        if self.peek == tok:
            return self.next()
        raise ParseException('expected tok %s, got %s' % (tok, self.peek))

    def assert_kind(self, kind):
        if self.peek.kind != kind:
            name = tkn.tok_name[kind]
            raise ParseException(
                "expected kind %s, got %s" % (name, self.peek))
        return self.next().val

    def assert_val(self, val):
        if self.peek.val != val:
            raise ParseException("expected val %s, got %s" % (val, self.peek))
        return self.next()

    def get_block(self):
        cnt = 0
        block = []
        for tok in self:
            block.append(tok)
            if tok.kind == tkn.DEDENT:
                if cnt == 0:
                    break
                cnt -= 1
            elif tok.kind == tkn.INDENT:
                cnt += 1
        return block[:-1]

    def assert_block(self):
        self.assert_val(':')
        self.assert_kind(tkn.NEWLINE)
        self.assert_kind(tkn.INDENT)


def print_tokens(tokens):
    for tok in tokens:
        tkn.printtoken(*tok)


def parse_block(gen, **kwargs):
    while gen.peek.kind != tkn.DEDENT:
        name = gen.assert_kind(tkn.NAME)
        if name not in kwargs:
            raise ParseException('unexpected name (%s)' % (name))
        kwargs[name](gen)
    gen.next()  # Consume `DEDENT`


VALID_TYPES = ['int', 'str', 'float', 'dict', 'list']
def get_type(name):
    if not name in VALID_TYPES:
        raise ParseException('invalid type, %s' % name)
    return eval(name)

def parse_event(gen, f):
    def parse_type(gen):
        def parse_params(gen):
            fields = []
            while gen.peek.kind != tkn.DEDENT:
                type = get_type(gen.assert_kind(tkn.NAME))
                id = gen.assert_kind(tkn.NAME)
                gen.assert_kind(tkn.NEWLINE)
                fields.append(target.Field(type, id))
            gen.next()
            return target.Struct(fields)

        def parse_union(gen):
            fmap = {}
            while gen.peek.kind != tkn.DEDENT:
                key = ast.literal_eval(gen.assert_kind(tkn.STRING))
                type = parse_type(gen)
                fmap[key] = type
            gen.next()
            return target.Union(fmap)

        if gen.peek.kind == tkn.NEWLINE:
            gen.next()  # Consume
            return target.Empty()
        name = gen.assert_kind(tkn.NAME)
        if name in SPECIAL_EVENTS:
            raise ParseException('%s is a special event name' % name)
        if name == 'struct':
            gen.assert_block()
            return parse_params(gen)
        elif name == 'union':
            gen.assert_block()
            return parse_union(gen)
        else:
            raise ParseException('type must be `param` or `union` got %s' % name)

    event_name = gen.assert_kind(tkn.NAME)
    event_type = parse_type(gen)
    f.events[event_name] = events.Event(event_name, event_type)


def get_base_indent(line):
    return len(line) - len(line.lstrip())


def normalize(block_str):
    block_str = block_str.strip('\\\n')
    lines = block_str.splitlines()
    base_indent = get_base_indent(lines[0])
    return '\n'.join([line[base_indent:] for line in lines])


def parse_decl(gen, f):
    gen.assert_block()
    f.decl = tkn.untokenize(map(lambda x: x.get_tuple(), gen.get_block()))


def buf_line(line):
    return BytesIO(line.strip()).readline

def get_till_end(gen):
    toks = []
    while not gen.empty:
        toks.append(gen.next().get_tuple())
    return tkn.untokenize(toks)

def parse_directive(line):
    def get_param(comma=False):
        if comma:
            gen.assert_val(',')
        return gen.assert_kind(tkn.NAME)

    def get_dst_name():
        gen.assert_val(':')
        return gen.assert_kind(tkn.NAME)

    if not line.strip().startswith('$'):
        return line
    il = get_base_indent(line)
    ret = line[:il]
    gen = TokenGen(tkn.generate_tokens(buf_line(line)))
    gen.assert_val('$')
    name = gen.assert_kind(tkn.NAME)
    if name == 'transition':
        next_state = get_param()
        ret += '%s().transition(%s(), "%s")' % \
            (target.GET_REACTOR_FUNC, target.GET_MODULE_FUNC, next_state)
    elif name == 'event':
        dst = get_dst_name()
        event_name, specs = get_event_name(gen)
        params = get_till_end(gen).strip() or 'None'
        ret += "%s = (%s(%s), [%s], %s)" % \
               (dst, target.GET_EVENT_FUNC, repr(event_name), ','.join(map(repr, specs)), params)
    elif name == 'pump':
        stream = get_param()
        evt = get_param()
        if stream == 'local':
            ret += '%s().submit(*%s)' % (target.GET_REACTOR_FUNC, evt)
        else:
            #Pump to socket
            ret += '%s.pump(*%s)' % (stream, evt)
    elif name == 'fire':
        stream = get_param()
        event_name, specs = get_event_name(gen)
        params = get_till_end(gen).strip() or 'None'
        args = '%s(%s), [%s], %s' % \
               (target.GET_EVENT_FUNC, repr(event_name), ','.join(map(repr, specs)), params)
        if stream == 'local':
            ret += '%s().submit(%s)' % (target.GET_REACTOR_FUNC, args)
        else:
            ret += '%s.pump(%s)' % (stream, args)
    elif name == 'prompt':
        prompt = gen.assert_kind(tkn.STRING)
        ret += '%s()._get_input(%s, %s())' % \
               (target.GET_REACTOR_FUNC, prompt, target.GET_MODULE_FUNC)
    elif name == 'exit':
        ret += '%s().stop()' % (target.GET_REACTOR_FUNC)
    else:
        raise ParseException('unknown directive (%s)' % name)
    if not gen.empty:
        raise ParseException('dangling in directive (%s)' % line.strip())
    return ret


def resolve_directives(func_str):
    return '\n'.join(map(parse_directive, func_str.splitlines()))


DOT_TOK = Token((tkn.OP, '.'))


def get_event_name(gen):
    name = gen.assert_kind(tkn.NAME)
    quals = []
    while gen.peek == DOT_TOK:
        gen.assert_tok(DOT_TOK)
        s = gen.assert_kind(tkn.STRING)
        quals.append(ast.literal_eval(s))
    return name, quals

SPECIAL_EVENTS = {
    'entry': ['prev'],
    'exit': ['next'],
    'connected': ['comm', 'remote'],
    'closed': ['comm', 'remote'],
    'input': ['input']
}

def parse_module(gen, f):
    def parse_state(gen):
        def parse_trap(gen):
            event_name, quals = get_event_name(gen)
            gen.assert_block()
            toks = map(lambda x: x.get_tuple(), gen.get_block())
            body = resolve_directives(tkn.untokenize(toks))
            func_name = target.get_func_name(mod._namespace)
            params = SPECIAL_EVENTS.get(event_name, ['ctx'])
            handler = mod.assemble_trap(func_name, body, state.name, params=params)
            if event_name in ('entry', 'exit'):
                if getattr(state, 'on_' + event_name) != None:
                    raise ParseException('multiple %s traps' % event_name)
                if len(quals) != 0:
                    raise ParseException('not expecting qualifiers')
                setattr(state, 'on_' + event_name, handler)
            elif event_name in ('connected', 'disconnected'):
                if len(quals) != 1:
                    raise ParseException("expecting only comm name as qualifier")
                cname = quals[0]
                if not cname in mod.comms:
                    raise ParseException("unknown comm %s" % cname)
                comm = mod.comms[cname]
                comm.add_listener(event_name, handler)
            elif event_name == 'input':
                mod.input_handlers.append(handler)
            elif event_name in f.events:
                event = f.events[event_name]
                event.trap(quals, handler)
            else:
                raise ParseException('Invalid event name, %s' % event_name)

        state_name = gen.assert_kind(tkn.NAME)
        state = target.ModState(state_name)
        gen.assert_block()
        parse_block(gen, on=parse_trap)
        mod.states[state_name] = state
        if mod.default is None:
            mod.default = state_name

    def parse_def(gen):
        def_state = gen.assert_kind(tkn.NAME)
        if def_state not in mod.states:
            raise ParseException('invalid `default` state %s' % def_state)
        mod.default = def_state
        gen.assert_kind(tkn.NEWLINE)

    def parse_globals(gen):
        gen.assert_block()
        toks = map(lambda x: x.get_tuple(), gen.get_block())
        mod.init_globals(tkn.untokenize(toks))

    def parse_comm(gen):
        v = gen.assert_kind(tkn.NAME)
        n = gen.assert_kind(tkn.NAME)
        event_name = gen.assert_kind(tkn.NAME)
        gen.assert_kind(tkn.NEWLINE)
        if not event_name in f.events:
            raise ParseException('unknown event %s' % event_name)
        event = f.events[event_name]
        if v == 'pipe':
            pipe = net.Pipe(n, event)
            mod.add_comm(pipe)
        elif v == 'port':
            port = net.Port(n, event)
            mod.add_comm(port)
        #TODO(vasuman): integrate channels
        else:
            raise ParseException('invalid comm type %s' % v)

    mod_name = gen.assert_kind(tkn.NAME)
    mod = target.SnekModule(mod_name, f)
    gen.assert_block()
    parse_block(gen,
                state=parse_state,
                default=parse_def,
                comm=parse_comm,
                vars=parse_globals)
    f.modules.append(mod)


def parse(readline):
    # TODO(vasuman): Preprocessor `#include`s
    tokens = tkn.generate_tokens(readline)
    gen = TokenGen(tokens)
    f = target.SnekFile()
    while not gen.empty:
        name = gen.assert_kind(tkn.NAME)
        if name == 'module':
            parse_module(gen, f)
        elif name == 'event':
            parse_event(gen, f)
        elif name == 'decl':
            if f.decl is not None:
                raise ParseException('multiple `decl` blocks!')
            parse_decl(gen, f)
        else:
            raise ParseException('unexpected in <toplevel> (%s)' % name)
    f.done_parse()
    return f


def load_file(f):
    return parse(f.readline)

# REMOVE
TEST_PROGRAM = '''
decl:
  import os
  PORT = os.getenv('PORT')

event Query union:
  "Hello"
  "Bye" struct:
    float f
    str s
  "Ok" union:
    "Meh"
    "Bleh" struct:
      int i
      str s
      dict m
      list l

module Test:
  comm pipe pi Query
  comm port po Query
  vars:
    a = 0
    b = {}
    c = []
  state init:
    on entry:
      print "Hello World", a, b, c
      po.listen(PORT_NUM)
      pi.connect(('127.0.0.1', PORT_NUM))
    on connected."pi":
      print 'connected to po'
      $event:e Query."Bye" (0.1, 'asa')
      $pump pi e
    on Query."Bye":
      print "Yea!! Got Remotely"
      print ctx.params, ctx.extra['comm'].name
    on Query."Ok"."Bleh":
      print 'ctx: ', ctx.specs
  state stop:
    on entry:
      print "exiting"
  default init
'''

def parse_string(s):
    import io
    tkn.tokenize(io.BytesIO(s).readline)
    return parse(io.BytesIO(s).readline)

if __name__ == '__main__':
    with open(sys.argv[1], 'rb') as f:
        parse(f.readline)

reload(target)
reload(events)
reload(net)
# END REMOVE
