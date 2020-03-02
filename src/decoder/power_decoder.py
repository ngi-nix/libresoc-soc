from nmigen import Module, Elaboratable, Signal
from power_enums import (Function, InternalOp, In1Sel, In2Sel, In3Sel,
                         OutSel, RC, LdstLen, CryIn, get_csv, single_bit_flags,
                         get_signal_name)


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
            row = {'unit': "NONE", 'internal op': "OP_ILLEGAL",
                   'in1': "RA", 'in2': 'NONE', 'in3': 'NONE', 'out': 'NONE',
                   'ldst len': 'NONE',
                   'rc' : 'NONE', 'cry in' : 'ZERO'}
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

    def __init__(self, width, opcodes, opint=True, suffix=None):
        self.opint = opint  # true if the opcode needs to be converted to int
        self.opcodes = opcodes
        self.opcode_in = Signal(width, reset_less=True)

        self.op = PowerOp()
        self.suffix = suffix
        self.width = width

    def suffix_mask(self):
        return ((1 << self.suffix[1]) - 1) - ((1 << self.suffix[0]) - 1)

    def divide_opcodes(self):
        divided = {}
        mask = self.suffix_mask()
        for row in self.opcodes:
            opcode = row['opcode']
            if self.opint:
                opcode = int(opcode, 0)
            key = opcode & mask >> (self.suffix[0])
            opcode = opcode >> self.suffix[1]
            if key not in divided:
                divided[key] = []
            r = row.copy()
            r['opcode'] = opcode
            divided[key].append(r)
        return divided

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        if self.suffix:
            opcodes = self.divide_opcodes()
            opc_in = Signal(self.suffix[1] - self.suffix[0], reset_less=True)
            comb += opc_in.eq(self.opcode_in[self.suffix[0]:self.suffix[1]])
            with m.Switch(opc_in):
                for key, row in opcodes.items():
                    subdecoder = PowerDecoder(width=self.width - opc_in.width,
                                              opcodes=row,
                                              opint=False)
                    setattr(m.submodules, "dec%d" % key, subdecoder)
                    comb += subdecoder.opcode_in.eq(self.opcode_in[self.suffix[1]:])
                    with m.Case(key):
                        comb += self.op.eq(subdecoder.op)

        else:
            with m.Switch(self.opcode_in):
                for row in self.opcodes:
                    opcode = row['opcode']
                    if self.opint:
                        opcode = int(opcode, 0)
                    if not row['unit']:
                        continue
                    with m.Case(opcode):
                        comb += self.op._eq(row)
                with m.Default():
                        comb += self.op._eq(None)
        return m

    def ports(self):
        return [self.opcode_in] + self.op.ports()

# how about this?
# if False:
#     pminor = (0, 6, [(19, "minor_19", (1,11)), # pass to 'splitter' function
#                      (30, "minor_30", (1,4)),
#                      (31, "minor_31", (1,11)), # pass to 'splitter' function
#                      (58, "minor_58", (0,1)),
#                      (62, "minor_62", (0,1)),
#                     ]

#     pdecode = PowerDecoder(6, "major", subcoders = pminor)
