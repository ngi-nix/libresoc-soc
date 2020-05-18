from nmutil.singlepipe import ControlBase
from nmutil.pipemodbase import PipeModBaseChain
from soc.alu.input_stage import ALUInputStage
from soc.alu.main_stage import ALUMainStage
from soc.alu.output_stage import ALUOutputStage

class ALUStages(PipeModBaseChain):
    def get_chain(self):
        inp = ALUInputStage(self.pspec)
        main = ALUMainStage(self.pspec)
        out = ALUOutputStage(self.pspec)
        return [inp, main, out]


class ALUBasePipe(ControlBase):
    def __init__(self, pspec):
        ControlBase.__init__(self)
        self.pipe1 = ALUStages(pspec)
        self._eqs = self.connect([self.pipe1])

    def elaborate(self, platform):
        m = ControlBase.elaborate(self, platform)
        m.submodules.pipe = self.pipe1
        m.d.comb += self._eqs
        return m
