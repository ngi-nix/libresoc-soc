from functools import wraps
from soc.decoder.orderedset import OrderedSet
from soc.decoder.selectable_int import SelectableInt, selectconcat

def create_args(reglist, extra=None):
    args = OrderedSet()
    for reg in reglist:
        args.add(reg)
    args = list(args)
    if extra:
        args = [extra] + args
    return args

class Mem:

    def __init__(self):
        self.mem = []
        for i in range(128):
            self.mem.append(i)

    def __call__(self, addr, sz):
        res = []
        for s in range(sz): # TODO: big/little-end
            res.append(SelectableInt(self.mem[addr.value + s], 8))
        print ("memread", addr, sz, res)
        return selectconcat(*res)

    def memassign(self, addr, sz, val):
        print ("memassign", addr, sz, val)
        for s in range(sz):
            byte = (val.value) >> (s*8) & 0xff # TODO: big/little-end
            self.mem[addr.value + s] = byte


class GPR(dict):
    def __init__(self, decoder, regfile):
        dict.__init__(self)
        self.sd = decoder
        for i in range(32):
            self[i] = SelectableInt(regfile[i], 64)

    def __call__(self, ridx):
        return self[ridx]

    def set_form(self, form):
        self.form = form

    def getz(self, rnum):
        #rnum = rnum.value # only SelectableInt allowed
        print("GPR getzero", rnum)
        if rnum == 0:
            return SelectableInt(0, 64)
        return self[rnum]

    def _get_regnum(self, attr):
        getform = self.sd.sigforms[self.form]
        rnum = getattr(getform, attr)
        return rnum

    def ___getitem__(self, attr):
        print("GPR getitem", attr)
        rnum = self._get_regnum(attr)
        return self.regfile[rnum]

    def dump(self):
        for i in range(len(self)):
            print("reg", i, hex(self[i].value))



class ISACaller:
    # decoder2 - an instance of power_decoder2
    # regfile - a list of initial values for the registers
    def __init__(self, decoder2, regfile):
        self.gpr = GPR(decoder2, regfile)
        self.mem = Mem()
        self.namespace = {'GPR': self.gpr,
                          'MEM': self.mem,
                          'memassign': self.memassign
                          }
        self.decoder = decoder2

    def memassign(self, ea, sz, val):
        self.mem.memassign(ea, sz, val)

    def prep_namespace(self):
        si = yield self.decoder.SI
        self.namespace.SI = SelectableInt(si, bits=16)

    def call(self, name):
        function, read_regs, uninit_regs, write_regs = self.instrs[name]
        input_names = create_args(read_regs | uninit_regs)
        print(input_names)

        inputs = []
        for name in input_names:
            regnum = yield getattr(self.decoder, name)
            print('reading reg %d' % regnum)
            inputs.append(self.gpr(regnum))
        print(inputs)
        results = function(self, *inputs)
        print(results)

        output_names = create_args(write_regs)
        for name, output in zip(output_names, results):
            regnum = yield getattr(self.decoder, name)
            print('writing reg %d' % regnum)
            self.gpr[regnum] = output


def inject():
    """ Decorator factory. """
    def variable_injector(func):
        @wraps(func)
        def decorator(*args, **kwargs):
            try:
                func_globals = func.__globals__  # Python 2.6+
            except AttributeError:
                func_globals = func.func_globals  # Earlier versions.

            context = args[0].namespace
            saved_values = func_globals.copy()  # Shallow copy of dict.
            func_globals.update(context)

            result = func(*args, **kwargs)
            #exec (func.__code__, func_globals)

            #finally:
            #    func_globals = saved_values  # Undo changes.

            return result

        return decorator

    return variable_injector

