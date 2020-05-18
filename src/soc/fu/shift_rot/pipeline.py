from nmutil.singlepipe import ControlBase
from nmutil.pipemodbase import PipeModBaseChain
from soc.fu.shift_rot.input_stage import ShiftRotInputStage
from soc.fu.shift_rot.main_stage import ShiftRotMainStage
from soc.fu.alu.output_stage import ALUOutputStage

class ShiftRotStages(PipeModBaseChain):
    def get_chain(self):
        inp = ShiftRotInputStage(self.pspec)
        main = ShiftRotMainStage(self.pspec)
        out = ALUOutputStage(self.pspec)
        return [inp, main, out]


class ShiftRotBasePipe(ControlBase):
    def __init__(self, pspec):
        ControlBase.__init__(self)
        self.pipe1 = ShiftRotStages(pspec)
        self._eqs = self.connect([self.pipe1])

    def elaborate(self, platform):
        m = ControlBase.elaborate(self, platform)
        m.submodules.pipe = self.pipe1
        m.d.comb += self._eqs
        return m
