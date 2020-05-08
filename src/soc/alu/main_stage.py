from nmigen import (Module, Signal)
from nmutil.pipemodbase import PipeModBase
from soc.alu.pipe_data import ALUInitialData, ALUOutputData
from ieee754.part.partsig import PartitionedSignal
from soc.decoder.power_enums import InternalOp


class ALUMainStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "main")

    def ispec(self):
        return ALUInitialData(self.pspec)

    def ospec(self):
        return ALUOutputData(self.pspec)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        add_output = Signal(self.i.a.width + 1, reset_less=True)
        comb += add_output.eq(self.i.a + self.i.b)


        with m.Switch(self.i.ctx.op.insn_type):
            with m.Case(InternalOp.OP_ADD):
                comb += self.o.o.eq(add_output)

        comb += self.o.ctx.eq(self.i.ctx)

        return m
