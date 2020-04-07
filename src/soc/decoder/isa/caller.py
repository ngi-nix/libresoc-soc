from functools import wraps
from soc.decoder.orderedset import OrderedSet
from soc.decoder.selectable_int import (FieldSelectableInt, SelectableInt,
                                        selectconcat)
from collections import namedtuple
import math

instruction_info = namedtuple('instruction_info',
                              'func read_regs uninit_regs write_regs ' + \
                              'special_regs op_fields form asmregs')


def create_args(reglist, extra=None):
    args = OrderedSet()
    for reg in reglist:
        args.add(reg)
    args = list(args)
    if extra:
        args = [extra] + args
    return args


class Mem:

    def __init__(self, bytes_per_word=8):
        self.mem = {}
        self.bytes_per_word = bytes_per_word
        self.word_log2 = math.ceil(math.log2(bytes_per_word))

    def _get_shifter_mask(self, width, remainder):
        shifter = ((self.bytes_per_word - width) - remainder) * \
            8  # bits per byte
        mask = (1 << (width * 8)) - 1
        return shifter, mask

    # TODO: Implement ld/st of lesser width
    def ld(self, address, width=8):
        remainder = address & (self.bytes_per_word - 1)
        address = address >> self.word_log2
        assert remainder & (width - 1) == 0, "Unaligned access unsupported!"
        if address in self.mem:
            val = self.mem[address]
        else:
            val = 0

        if width != self.bytes_per_word:
            shifter, mask = self._get_shifter_mask(width, remainder)
            val = val & (mask << shifter)
            val >>= shifter
        print("Read {:x} from addr {:x}".format(val, address))
        return val

    def st(self, address, value, width=8):
        remainder = address & (self.bytes_per_word - 1)
        address = address >> self.word_log2
        assert remainder & (width - 1) == 0, "Unaligned access unsupported!"
        print("Writing {:x} to addr {:x}".format(value, address))
        if width != self.bytes_per_word:
            if address in self.mem:
                val = self.mem[address]
            else:
                val = 0
            shifter, mask = self._get_shifter_mask(width, remainder)
            val &= ~(mask << shifter)
            val |= value << shifter
            self.mem[address] = val
        else:
            self.mem[address] = value

    def __call__(self, addr, sz):
        val = self.ld(addr.value, sz)
        print ("memread", addr, sz, val)
        return SelectableInt(val, sz*8)

    def memassign(self, addr, sz, val):
        print ("memassign", addr, sz, val)
        self.st(addr.value, val.value, sz)


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
        for i in range(0, len(self), 8):
            s = []
            for j in range(8):
                s.append("%08x" % self[i+j].value)
            s = ' '.join(s)
            print("reg", "%2d" % i, s)

class PC:
    def __init__(self, pc_init=0):
        self.CIA = SelectableInt(pc_init, 64)
        self.NIA = self.CIA + SelectableInt(4, 64)

    def update(self, namespace):
        self.CIA = self.NIA
        self.NIA = self.CIA + SelectableInt(4, 64)
        namespace['CIA'] = self.CIA
        namespace['NIA'] = self.NIA


class ISACaller:
    # decoder2 - an instance of power_decoder2
    # regfile - a list of initial values for the registers
    def __init__(self, decoder2, regfile):
        self.gpr = GPR(decoder2, regfile)
        self.mem = Mem()
        self.pc = PC()
        # TODO, needed here:
        # 4.4.4 III p971 SPR (same as GPR except for SPRs - best done as a dict
        # FPR (same as GPR except for FP nums)
        # 4.2.2 p124 FPSCR (definitely "separate" - not in SPR)
        #            note that mffs, mcrfs, mtfsf "manage" this FPSCR
        # 2.3.1 CR (and sub-fields CR0..CR6 - CR0 SO comes from XER.SO)
        #         note that mfocrf, mfcr, mtcr, mtocrf, mcrxrx "manage" CRs
        # 2.3.2 LR   (actually SPR #8)
        # 2.3.3 CTR  (actually SPR #9)
        # 2.3.4 TAR  (actually SPR #815)
        # 3.2.2 p45 XER  (actually SPR #0)
        # 3.2.3 p46 p232 VRSAVE (actually SPR #256)

        # create CR then allow portions of it to be "selectable" (below)
        self.cr = SelectableInt(0, 32)

        self.namespace = {'GPR': self.gpr,
                          'MEM': self.mem,
                          'memassign': self.memassign,
                          'NIA': self.pc.NIA,
                          'CIA': self.pc.CIA,
                          'CR': self.cr,
                          }

        # field-selectable versions of Condition Register TODO check bitranges?
        self.crl = []
        for i in range(8):
            bits = tuple(range(i*4, (i+1)*4))# errr... maybe?
            _cr = FieldSelectableInt(self.cr, bits)
            self.crl.append(_cr)
            self.namespace["CR%d" % i] = _cr

        self.decoder = decoder2

    def memassign(self, ea, sz, val):
        self.mem.memassign(ea, sz, val)

    def prep_namespace(self, formname, op_fields):
        # TODO: get field names from form in decoder*1* (not decoder2)
        # decoder2 is hand-created, and decoder1.sigform is auto-generated
        # from spec
        # then "yield" fields only from op_fields rather than hard-coded
        # list, here.
        fields = self.decoder.sigforms[formname]
        for name in op_fields:
            sig = getattr(fields, name)
            val = yield sig
            self.namespace[name] = SelectableInt(val, sig.width)

    def call(self, name):
        # TODO, asmregs is from the spec, e.g. add RT,RA,RB
        # see http://bugs.libre-riscv.org/show_bug.cgi?id=282
        info = self.instrs[name]
        yield from self.prep_namespace(info.form, info.op_fields)

        input_names = create_args(info.read_regs | info.uninit_regs |
                                  info.special_regs)
        print(input_names)

        inputs = []
        for name in input_names:
            regnum = yield getattr(self.decoder, name)
            regname = "_" + name
            self.namespace[regname] = regnum
            print('reading reg %d' % regnum)
            inputs.append(self.gpr(regnum))
        print(inputs)
        results = info.func(self, *inputs)
        print(results)

        if info.write_regs:
            output_names = create_args(info.write_regs)
            for name, output in zip(output_names, results):
                regnum = yield getattr(self.decoder, name)
                print('writing reg %d' % regnum)
                if output.bits > 64:
                    output = SelectableInt(output.value, 64)
                self.gpr[regnum] = output
        self.pc.update(self.namespace)


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

