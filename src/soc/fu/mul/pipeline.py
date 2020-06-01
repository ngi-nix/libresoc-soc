from nmutil.singlepipe import ControlBase
from nmutil.pipemodbase import PipeModBaseChain
from soc.fu.shift_rot.input_stage import ShiftRotInputStage
from soc.fu.shift_rot.main_stage import ShiftRotMainStage
from soc.fu.alu.output_stage import ALUOutputStage

class MulStages1(PipeModBaseChain):
    def get_chain(self):
        inp = ALUInputStage(self.pspec)
        main = MulMainStage1(self.pspec)
        return [inp, main]

class MulStages2(PipeModBaseChain):
    def get_chain(self):
        main2 = MulMainStage2(self.pspec)
        out = ALUOutputStage(self.pspec)
        return [main2, out]


class ShiftRotBasePipe(ControlBase):
    def __init__(self, pspec):
        ControlBase.__init__(self)
        self.pspec = pspec
        self.pipe1 = MulStages1(pspec)
        self.pipe2 = MulStages2(pspec)
        self._eqs = self.connect([self.pipe1, self.pipe2])

    def elaborate(self, platform):
        m = ControlBase.elaborate(self, platform)
        m.submodules.pipe = self.pipe1
        m.d.comb += self._eqs
        return m
