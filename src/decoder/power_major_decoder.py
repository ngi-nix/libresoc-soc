from nmigen import Module, Elaboratable, Signal
import csv
import os
from enum import Enum, unique


@unique
class Function(Enum):
    ALU = 0
    LDST = 1


@unique
class InternalOp(Enum):
    OP_ADD = 0
    OP_AND = 1
    OP_B = 2
    OP_BC = 3
    OP_CMP = 4
    OP_LOAD = 5
    OP_MUL_L64 = 6
    OP_OR = 7
    OP_RLC = 8
    OP_STORE = 9
    OP_TDI = 10
    OP_XOR = 11


@unique
class In1Sel(Enum):
    RA = 0
    RA_OR_ZERO = 1
    NONE = 2
    SPR = 3


@unique
class In2Sel(Enum):
    CONST_SI = 0
    CONST_SI_HI = 1
    CONST_UI = 2
    CONST_UI_HI = 3
    CONST_LI = 4
    CONST_BD = 5
    CONST_SH32 = 6
    RB = 7


@unique
class In3Sel(Enum):
    NONE = 0
    RS = 1


@unique
class OutSel(Enum):
    RT = 0
    RA = 1
    NONE = 2
    SPR = 3


@unique
class LdstLen(Enum):
    NONE = 0
    is1B = 1
    is2B = 2
    is4B = 3


@unique
class RC(Enum):
    NONE = 0
    ONE = 1
    RC = 2


# names of the fields in major.csv that don't correspond to an enum
single_bit_flags = ['CR in', 'CR out', 'inv A', 'inv out', 'cry in',
                    'cry out', 'BR', 'sgn ext', 'upd', 'rsrv', '32b',
                    'sgn', 'lk', 'sgl pipe']


def get_signal_name(name):
    return name.lower().replace(' ', '_')


def get_csv(name):
    file_dir = os.path.dirname(os.path.realpath(__file__))
    with open(os.path.join(file_dir, name)) as csvfile:
        reader = csv.DictReader(csvfile)
        return list(reader)


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
