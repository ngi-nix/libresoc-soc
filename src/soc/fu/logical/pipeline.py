from nmutil.singlepipe import ControlBase
from nmutil.pipemodbase import PipeModBaseChain
from soc.fu.logical.input_stage import LogicalInputStage
from soc.fu.logical.main_stage import LogicalMainStage
from soc.fu.logical.output_stage import LogicalOutputStage


class LogicalStages1(PipeModBaseChain):
    def get_chain(self):
        inp = LogicalInputStage(self.pspec)
        main = LogicalMainStage(self.pspec)
        return [inp, main]


class LogicalStages2(PipeModBaseChain):
    def get_chain(self):
        out = LogicalOutputStage(self.pspec)
        return [out]


class LogicalBasePipe(ControlBase):
    def __init__(self, pspec):
        ControlBase.__init__(self)
        self.pspec = pspec
        self.pipe1 = LogicalStages1(pspec)
        self.pipe2 = LogicalStages2(pspec)
        self._eqs = self.connect([self.pipe1, self.pipe2])

    def elaborate(self, platform):
        m = ControlBase.elaborate(self, platform)
        m.submodules.logical_pipe1 = self.pipe1
        m.submodules.logical_pipe2 = self.pipe2
        m.d.comb += self._eqs
        return m
