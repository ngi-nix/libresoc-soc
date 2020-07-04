from nmutil.singlepipe import ControlBase
from nmutil.pipemodbase import PipeModBaseChain
from soc.fu.spr.main_stage import SPRMainStage

class SPRStages(PipeModBaseChain):
    def get_chain(self):
        main = SPRMainStage(self.pspec)
        return [main]


class SPRBasePipe(ControlBase):
    def __init__(self, pspec):
        ControlBase.__init__(self)
        self.pspec = pspec
        self.pipe1 = SPRStages(pspec)
        self._eqs = self.connect([self.pipe1])

    def elaborate(self, platform):
        m = ControlBase.elaborate(self, platform)
        m.submodules.pipe = self.pipe1
        m.d.comb += self._eqs
        return m
