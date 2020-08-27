from nmutil.singlepipe import ControlBase
from nmutil.pipemodbase import PipeModBaseChain
from soc.fu.shift_rot.input_stage import ShiftRotInputStage
from soc.fu.shift_rot.main_stage import ShiftRotMainStage
from soc.fu.shift_rot.output_stage import ShiftRotOutputStage

class ShiftRotStages(PipeModBaseChain):
    def get_chain(self):
        inp = ShiftRotInputStage(self.pspec)
        main = ShiftRotMainStage(self.pspec)
        return [inp, main]


class ShiftRotStageEnd(PipeModBaseChain):
    def get_chain(self):
        out = ShiftRotOutputStage(self.pspec)
        return [out]


class ShiftRotBasePipe(ControlBase):
    def __init__(self, pspec):
        ControlBase.__init__(self)
        self.pspec = pspec
        self.pipe1 = ShiftRotStages(pspec)
        self.pipe2 = ShiftRotStageEnd(pspec)
        self._eqs = self.connect([self.pipe1, self.pipe2])

    def elaborate(self, platform):
        m = ControlBase.elaborate(self, platform)
        m.submodules.pipe1 = self.pipe1
        m.submodules.pipe2 = self.pipe2
        m.d.comb += self._eqs
        return m
