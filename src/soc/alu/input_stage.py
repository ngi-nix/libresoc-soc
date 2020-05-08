from nmigen import (Module, Signal, Cat, Const, Mux, Repl, signed,
                    unsigned)
from nmutil.pipemodbase import PipeModBase
from soc.alu.pipe_data import ALUInitialData


class ALUInputStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "input")

    def ispec(self):
        return ALUInitialData(self.pspec)

    def ospec(self):
        return ALUInitialData(self.pspec)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        comb += self.o.op.eq(self.i.op)

        return m
