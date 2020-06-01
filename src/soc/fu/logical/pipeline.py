from nmutil.singlepipe import ControlBase
from nmutil.pipemodbase import PipeModBaseChain
from soc.fu.logical.input_stage import LogicalInputStage
from soc.fu.logical.main_stage import LogicalMainStage
from soc.fu.logical.output_stage import LogicalOutputStage

class LogicalStages(PipeModBaseChain):
    def get_chain(self):
        inp = LogicalInputStage(self.pspec)
        main = LogicalMainStage(self.pspec)
        out = LogicalOutputStage(self.pspec)
        return [inp, main, out]


class LogicalBasePipe(ControlBase):
    def __init__(self, pspec):
        ControlBase.__init__(self)
        self.pspec = pspec
        self.pipe1 = LogicalStages(pspec)
        self._eqs = self.connect([self.pipe1])

    def elaborate(self, platform):
        m = ControlBase.elaborate(self, platform)
        m.submodules.pipe = self.pipe1
        m.d.comb += self._eqs
        return m
