from nmutil.singlepipe import ControlBase
from nmutil.pipemodbase import PipeModBaseChain
from soc.fu.alu.input_stage import ALUInputStage
from soc.fu.logical.main_stage import LogicalMainStage
from soc.fu.alu.output_stage import ALUOutputStage


class DivStagesStart(PipeModBaseChain):
    def get_chain(self):
        inp = ALUInputStage(self.pspec)
        main = DivMainStage1(self.pspec)
        return [inp, main, out]

class DivStagesEnd(PipeModBaseChain):
    def get_chain(self):
        main = DivMainStage2(self.pspec)
        out = ALUOutputStage(self.pspec)
        return [inp, main, out]


class LogicalBasePipe(ControlBase):
    def __init__(self, pspec):
        ControlBase.__init__(self)
        self.pipe1 = DivStagesStart(pspec)
        self.pipe5 = DivStagesEnd(pspec)
        self._eqs = self.connect([self.pipe1, self.pipe5])

    def elaborate(self, platform):
        m = ControlBase.elaborate(self, platform)
        m.submodules.pipe1 = self.pipe1
        m.submodules.pipe5 = self.pipe5
        m.d.comb += self._eqs
        return m
