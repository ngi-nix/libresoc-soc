from nmigen import Module, Elaboratable, Signal
import csv
import os
from enum import Enum, unique

class Function(Enum):
    ALU = 0
    LDST = 1

def get_csv(name):
    file_dir = os.path.dirname(os.path.realpath(__file__))
    with open(os.path.join(file_dir, name)) as csvfile:
        reader = csv.DictReader(csvfile)
        return list(reader)

major_opcodes = get_csv("major.csv")

class PowerDecoder(Elaboratable):
    def __init__(self):
        self.opcode_in = Signal(6, reset_less=True)

        self.function_unit = Signal(Function, reset_less=True)
    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        with m.Switch(self.opcode_in):
            for row in major_opcodes:
                opcode = int(row['opcode'])
                with m.Case(opcode):
                    comb += self.function_unit.eq(Function[row['unit']])
        return m



    
