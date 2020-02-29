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
    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        with m.Switch(self.opcode_in):
            for row in major_opcodes:
                opcode = int(row['opcode'])
                with m.Case(opcode):
                    comb += self.function_unit.eq(Function[row['unit']])
                    comb += self.internal_op.eq(InternalOp[row['internal op']])
        return m



    
