from functools import wraps
from soc.decoder.orderedset import OrderedSet
from soc.decoder.selectable_int import (FieldSelectableInt, SelectableInt,
                                        selectconcat)
from soc.decoder.power_enums import spr_dict, XER_bits
from soc.decoder.helpers import exts
from collections import namedtuple
import math

instruction_info = namedtuple('instruction_info',
                              'func read_regs uninit_regs write_regs ' + \
                              'special_regs op_fields form asmregs')

special_sprs = {
    'LR': 8,
    'CTR': 9,
    'TAR': 815,
    'XER': 1,
    'VRSAVE': 256}


def create_args(reglist, extra=None):
    args = OrderedSet()
    for reg in reglist:
        args.add(reg)
    args = list(args)
    if extra:
        args = [extra] + args
    return args


class Mem:

    def __init__(self, bytes_per_word=8, initial_mem=None):
        self.mem = {}
        self.bytes_per_word = bytes_per_word
        self.word_log2 = math.ceil(math.log2(bytes_per_word))
        if initial_mem:
            for addr, (val, width) in initial_mem.items():
                self.st(addr, val, width)

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
        self.CIA = namespace['NIA'].narrow(64)
        self.NIA = self.CIA + SelectableInt(4, 64)
        namespace['CIA'] = self.CIA
        namespace['NIA'] = self.NIA


class SPR(dict):
    def __init__(self, dec2, initial_sprs={}):
        self.sd = dec2
        dict.__init__(self)
        self.update(initial_sprs)

    def __getitem__(self, key):
        # if key in special_sprs get the special spr, otherwise return key
        if isinstance(key, SelectableInt):
            key = key.value
        key = special_sprs.get(key, key)
        if key in self:
            return dict.__getitem__(self, key)
        else:
            info = spr_dict[key]
            dict.__setitem__(self, key, SelectableInt(0, info.length))
            return dict.__getitem__(self, key)

    def __setitem__(self, key, value):
        if isinstance(key, SelectableInt):
            key = key.value
        key = special_sprs.get(key, key)
        dict.__setitem__(self, key, value)

    def __call__(self, ridx):
        return self[ridx]
        
        

class ISACaller:
    # decoder2 - an instance of power_decoder2
    # regfile - a list of initial values for the registers
    def __init__(self, decoder2, regfile, initial_sprs=None, initial_cr=0,
                       initial_mem=None):
        if initial_sprs is None:
            initial_sprs = {}
        if initial_mem is None:
            initial_mem = {}
        self.gpr = GPR(decoder2, regfile)
        self.mem = Mem(initial_mem=initial_mem)
        self.pc = PC()
        self.spr = SPR(decoder2, initial_sprs)
        # TODO, needed here:
        # FPR (same as GPR except for FP nums)
        # 4.2.2 p124 FPSCR (definitely "separate" - not in SPR)
        #            note that mffs, mcrfs, mtfsf "manage" this FPSCR
        # 2.3.1 CR (and sub-fields CR0..CR6 - CR0 SO comes from XER.SO)
        #         note that mfocrf, mfcr, mtcr, mtocrf, mcrxrx "manage" CRs
        #         -- Done
        # 2.3.2 LR   (actually SPR #8) -- Done
        # 2.3.3 CTR  (actually SPR #9) -- Done
        # 2.3.4 TAR  (actually SPR #815)
        # 3.2.2 p45 XER  (actually SPR #1) -- Done
        # 3.2.3 p46 p232 VRSAVE (actually SPR #256)

        # create CR then allow portions of it to be "selectable" (below)
        self._cr = SelectableInt(initial_cr, 64) # underlying reg
        self.cr = FieldSelectableInt(self._cr, list(range(32,64)))

        # "undefined", just set to variable-bit-width int (use exts "max")
        self.undefined = SelectableInt(0, 256) # TODO, not hard-code 256!

        self.namespace = {'GPR': self.gpr,
                          'MEM': self.mem,
                          'SPR': self.spr,
                          'memassign': self.memassign,
                          'NIA': self.pc.NIA,
                          'CIA': self.pc.CIA,
                          'CR': self.cr,
                          'undefined': self.undefined,
                          'mode_is_64bit': True,
                          'SO': XER_bits['SO']
                          }

        # field-selectable versions of Condition Register TODO check bitranges?
        self.crl = []
        for i in range(8):
            bits = tuple(range(i*4, (i+1)*4))# errr... maybe?
            _cr = FieldSelectableInt(self.cr, bits)
            self.crl.append(_cr)
            self.namespace["CR%d" % i] = _cr

        self.decoder = decoder2.dec
        self.dec2 = decoder2

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
            if name == 'spr':
                sig = getattr(fields, name.upper())
            else:
                sig = getattr(fields, name)
            val = yield sig
            if name in ['BF', 'BFA']:
                self.namespace[name] = val
            else:
                self.namespace[name] = SelectableInt(val, sig.width)

        self.namespace['XER'] = self.spr['XER']
        self.namespace['CA'] = self.spr['XER'][XER_bits['CA']].value

    def handle_carry_(self, inputs, outputs):
        inv_a = yield self.dec2.e.invert_a
        if inv_a:
            inputs[0] = ~inputs[0]

        imm_ok = yield self.dec2.e.imm_data.ok
        if imm_ok:
            imm = yield self.dec2.e.imm_data.data
            inputs.append(SelectableInt(imm, 64))
        assert len(outputs) >= 1
        output = outputs[0]
        gts = [(x > output) for x in inputs]
        print(gts)
        cy = 1 if any(gts) else 0
        self.spr['XER'][XER_bits['CA']] = cy


        # 32 bit carry
        gts = [(x[32:64] > output[32:64]) == SelectableInt(1, 1)
               for x in inputs]
        cy32 = 1 if any(gts) else 0
        self.spr['XER'][XER_bits['CA32']] = cy32

    def handle_overflow(self, inputs, outputs):
        inv_a = yield self.dec2.e.invert_a
        if inv_a:
            inputs[0] = ~inputs[0]

        imm_ok = yield self.dec2.e.imm_data.ok
        if imm_ok:
            imm = yield self.dec2.e.imm_data.data
            inputs.append(SelectableInt(imm, 64))
        assert len(outputs) >= 1
        if len(inputs) >= 2:
            output = outputs[0]
            input_sgn = [exts(x.value, x.bits) < 0 for x in inputs]
            output_sgn = exts(output.value, output.bits) < 0
            ov = 1 if input_sgn[0] == input_sgn[1] and \
                output_sgn != input_sgn[0] else 0

            self.spr['XER'][XER_bits['OV']] = ov
            so = self.spr['XER'][XER_bits['SO']]
            so = so | ov
            self.spr['XER'][XER_bits['SO']] = so



    def handle_comparison(self, outputs):
        out = outputs[0]
        out = exts(out.value, out.bits)
        zero = SelectableInt(out == 0, 1)
        positive = SelectableInt(out > 0, 1)
        negative = SelectableInt(out < 0, 1)
        SO = self.spr['XER'][XER_bits['SO']]
        cr_field = selectconcat(negative, positive, zero, SO)
        self.crl[0].eq(cr_field)

    def set_pc(self, pc_val):
        self.namespace['NIA'] = SelectableInt(pc_val, 64)
        self.pc.update(self.namespace)
        

    def call(self, name):
        # TODO, asmregs is from the spec, e.g. add RT,RA,RB
        # see http://bugs.libre-riscv.org/show_bug.cgi?id=282
        info = self.instrs[name]
        yield from self.prep_namespace(info.form, info.op_fields)

        # preserve order of register names
        input_names = create_args(list(info.read_regs) + list(info.uninit_regs))
        print(input_names)

        # main registers (RT, RA ...)
        inputs = []
        for name in input_names:
            regnum = yield getattr(self.decoder, name)
            regname = "_" + name
            self.namespace[regname] = regnum
            print('reading reg %d' % regnum)
            inputs.append(self.gpr(regnum))

        # "special" registers
        for special in info.special_regs:
            if special in special_sprs:
                inputs.append(self.spr[special])
            else:
                inputs.append(self.namespace[special])

        print(inputs)
        results = info.func(self, *inputs)
        print(results)

        carry_en = yield self.dec2.e.output_carry
        if carry_en:
            yield from self.handle_carry_(inputs, results)
        ov_en = yield self.dec2.e.oe
        if ov_en:
            yield from self.handle_overflow(inputs, results)
        rc_en = yield self.dec2.e.rc.data
        if rc_en:
            self.handle_comparison(results)

        # any modified return results?
        if info.write_regs:
            output_names = create_args(info.write_regs)
            for name, output in zip(output_names, results):
                if isinstance(output, int):
                    output = SelectableInt(output, 256)
                if name in info.special_regs:
                    print('writing special %s' % name, output)
                    if name in special_sprs:
                        self.spr[name] = output
                    else:
                        self.namespace[name].eq(output)
                else:
                    regnum = yield getattr(self.decoder, name)
                    print('writing reg %d %s' % (regnum, str(output)))
                    if output.bits > 64:
                        output = SelectableInt(output.value, 64)
                    self.gpr[regnum] = output

        # update program counter
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
            args[0].namespace = func_globals
            #exec (func.__code__, func_globals)

            #finally:
            #    func_globals = saved_values  # Undo changes.

            return result

        return decorator

    return variable_injector

