from nmigen import Module, Elaboratable, Signal
from power_enums import (Function, InternalOp, In1Sel, In2Sel, In3Sel,
                         OutSel, RC, LdstLen, CryIn, get_csv, single_bit_flags,
                         get_signal_name, default_values)
from collections import namedtuple

# TODO - list of these into PowerDecoder
Decoder = namedtuple("Decoder", ["width", "pattern", "csv", "opint",
                                       "bitsel", "suffix", "subdecoders"])

Subdecoder = namedtuple("Subdecoder", ["pattern", "csv", "opint",
                                       "bitsel", "suffix"])


class PowerOp:
    """PowerOp: spec for execution.  op type (ADD etc.) reg specs etc.
    """

    def __init__(self):
        self.function_unit = Signal(Function, reset_less=True)
        self.internal_op = Signal(InternalOp, reset_less=True)
        self.in1_sel = Signal(In1Sel, reset_less=True)
        self.in2_sel = Signal(In2Sel, reset_less=True)
        self.in3_sel = Signal(In3Sel, reset_less=True)
        self.out_sel = Signal(OutSel, reset_less=True)
        self.ldst_len = Signal(LdstLen, reset_less=True)
        self.rc_sel = Signal(RC, reset_less=True)
        self.cry_in = Signal(CryIn, reset_less=True)
        for bit in single_bit_flags:
            name = get_signal_name(bit)
            setattr(self, name, Signal(reset_less=True, name=name))

    def _eq(self, row=None):
        if row is None:
            row = default_values
        res = [self.function_unit.eq(Function[row['unit']]),
               self.internal_op.eq(InternalOp[row['internal op']]),
               self.in1_sel.eq(In1Sel[row['in1']]),
               self.in2_sel.eq(In2Sel[row['in2']]),
               self.in3_sel.eq(In3Sel[row['in3']]),
               self.out_sel.eq(OutSel[row['out']]),
               self.ldst_len.eq(LdstLen[row['ldst len']]),
               self.rc_sel.eq(RC[row['rc']]),
               self.cry_in.eq(CryIn[row['cry in']]),
               ]
        for bit in single_bit_flags:
            sig = getattr(self, get_signal_name(bit))
            res.append(sig.eq(int(row.get(bit, 0))))
        return res

    def eq(self, otherop):
        res = [self.function_unit.eq(otherop.function_unit),
               self.internal_op.eq(otherop.internal_op),
               self.in1_sel.eq(otherop.in1_sel),
               self.in2_sel.eq(otherop.in2_sel),
               self.in3_sel.eq(otherop.in3_sel),
               self.out_sel.eq(otherop.out_sel),
               self.rc_sel.eq(otherop.rc_sel),
               self.ldst_len.eq(otherop.ldst_len),
               self.cry_in.eq(otherop.cry_in)]
        for bit in single_bit_flags:
            sig = getattr(self, get_signal_name(bit))
            res.append(sig.eq(getattr(otherop, get_signal_name(bit))))
        return res

    def ports(self):
        regular = [self.function_unit,
                   self.in1_sel,
                   self.in2_sel,
                   self.in3_sel,
                   self.out_sel,
                   self.ldst_len,
                   self.rc_sel,
                   self.internal_op]
        single_bit_ports = [getattr(self, get_signal_name(x))
                            for x in single_bit_flags]
        return regular + single_bit_ports


class PowerDecoder(Elaboratable):
    """PowerDecoder - decodes an incoming opcode into the type of operation
    """

    def __init__(self,
                width, opcodes, *,            # TODO
                 bitsel, subdecoders=[],      # all of these
                 opint=True,                  # to become
                 suffix=None):                # a *list* of arguments
        self.opint = opint  # true if the opcode needs to be converted to int
        self.opcodes = opcodes
        self.opcode_in = Signal(width, reset_less=True)

        self.op = PowerOp()
        self.suffix = suffix
        if suffix is not None and suffix >= width:
            self.suffix = None
        self.bitsel = bitsel
        self.subdecoders = subdecoders
        self.width = width

    def suffix_mask(self):
        return ((1 << self.suffix) - 1)

    def divide_opcodes(self):
        divided = {}
        mask = self.suffix_mask()
        print("mask", hex(mask))
        for row in self.opcodes:
            opcode = row['opcode']
            if self.opint and '-' not in opcode:
                opcode = int(opcode, 0)
            key = opcode & mask
            opcode = opcode >> self.suffix
            if key not in divided:
                divided[key] = []
            r = row.copy()
            r['opcode'] = opcode
            divided[key].append(r)
        return divided

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        opcode_switch = Signal(self.bitsel[1] - self.bitsel[0], reset_less=True)
        comb += opcode_switch.eq(self.opcode_in[self.bitsel[0]:self.bitsel[1]])
        if self.suffix:
            opcodes = self.divide_opcodes()
            opc_in = Signal(self.suffix, reset_less=True)
            comb += opc_in.eq(opcode_switch[:self.suffix])
            with m.Switch(opc_in):
                for key, row in opcodes.items():
                    bitsel = (self.suffix+self.bitsel[0], self.bitsel[1])
                    subdecoder = PowerDecoder(width=32,
                                              opcodes=row,
                                              bitsel=bitsel,
                                              opint=False)
                    setattr(m.submodules, "dec_sub%d" % key, subdecoder)
                    comb += subdecoder.opcode_in.eq(self.opcode_in)
                    with m.Case(key):
                        comb += self.op.eq(subdecoder.op)

        else:
            comb += self.op._eq(None) # default case
            # TODO: arguments, here (all of them) need to be a list.
            # a for-loop around the *list* of decoder args.
            with m.Switch(opcode_switch):
                self.handle_subdecoders(m)
                for row in self.opcodes:
                    opcode = row['opcode']
                    if self.opint and '-' not in opcode:
                        opcode = int(opcode, 0)
                    if not row['unit']:
                        continue
                    with m.Case(opcode):
                        comb += self.op._eq(row)
        return m

    def handle_subdecoders(self, m):
        for dec in self.subdecoders:
            subdecoder = PowerDecoder(width=self.width,
                                      opcodes=dec.csv,
                                      opint=dec.opint,
                                      suffix=dec.suffix,
                                      bitsel=dec.bitsel)

            setattr(m.submodules, "dec%d" % dec.pattern, subdecoder)
            m.d.comb += subdecoder.opcode_in.eq(self.opcode_in)
            with m.Case(dec.pattern):
                m.d.comb += self.op.eq(subdecoder.op)

    def ports(self):
        return [self.opcode_in] + self.op.ports()


pminor = [
    Subdecoder(pattern=19, csv=get_csv("minor_19.csv"),
               opint=True, bitsel=(1, 11), suffix=None),
    Subdecoder(pattern=30, csv=get_csv("minor_30.csv"),
               opint=True, bitsel=(1, 5), suffix=None),
    Subdecoder(pattern=31, csv=get_csv("minor_31.csv"),
               opint=True, bitsel=(1, 11), suffix=5),
    Subdecoder(pattern=58, csv=get_csv("minor_58.csv"),
               opint=True, bitsel=(0, 2), suffix=None),
    Subdecoder(pattern=62, csv=get_csv("minor_62.csv"),
               opint=True, bitsel=(0, 2), suffix=None),
]

opcodes = get_csv("major.csv")
pdecode = PowerDecoder(32, opcodes, bitsel=(26, 32), subdecoders=pminor)
