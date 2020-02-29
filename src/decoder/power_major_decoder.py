from nmigen import Module, Elaboratable, Signal
from power_enums import (Function, InternalOp, In1Sel, In2Sel, In3Sel,
                         OutSel, RC, LdstLen, CryIn, get_csv)


# names of the fields in major.csv that don't correspond to an enum
single_bit_flags = ['CR in', 'CR out', 'inv A', 'inv out',
                    'cry out', 'BR', 'sgn ext', 'upd', 'rsrv', '32b',
                    'sgn', 'lk', 'sgl pipe']


def get_signal_name(name):
    return name.lower().replace(' ', '_')




major_opcodes = get_csv("major.csv")


class PowerMajorDecoder(Elaboratable):
    def __init__(self):
        self.opcode_in = Signal(6, reset_less=True)

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
            setattr(self, name,
                    Signal(reset_less=True, name=name))

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        with m.Switch(self.opcode_in):
            for row in major_opcodes:
                opcode = int(row['opcode'])
                with m.Case(opcode):
                    comb += self.function_unit.eq(Function[row['unit']])
                    comb += self.internal_op.eq(InternalOp[row['internal op']])
                    comb += self.in1_sel.eq(In1Sel[row['in1']])
                    comb += self.in2_sel.eq(In2Sel[row['in2']])
                    comb += self.in3_sel.eq(In3Sel[row['in3']])
                    comb += self.out_sel.eq(OutSel[row['out']])
                    comb += self.ldst_len.eq(LdstLen[row['ldst len']])
                    comb += self.rc_sel.eq(RC[row['rc']])
                    comb += self.cry_in.eq(CryIn[row['cry in']])
                    for bit in single_bit_flags:
                        sig = getattr(self, get_signal_name(bit))
                        comb += sig.eq(int(row[bit]))
        return m

    def ports(self):
        regular =[self.opcode_in,
                  self.function_unit,
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
