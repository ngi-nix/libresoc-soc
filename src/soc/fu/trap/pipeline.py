from nmutil.singlepipe import ControlBase
from nmutil.pipemodbase import PipeModBaseChain
from soc.fu.trap.main_stage import TrapMainStage
from soc.fu.trap.pipe_data import TrapInputData
from nmutil.pipemodbase import PipeModBase
from nmigen import Module

# gives a 1-clock delay to stop combinatorial link between in and out
class DummyTrapStage(PipeModBase):
    def __init__(self, pspec): super().__init__(pspec, "dummy")
    def ispec(self): return TrapInputData(self.pspec)
    def ospec(self): return TrapInputData(self.pspec)

    def elaborate(self, platform):
        m = Module()
        m.d.comb += self.o.eq(self.i) # pass-through output
        return m


class TrapDummyStages(PipeModBaseChain):
    def get_chain(self):
        dummy = DummyTrapStage(self.pspec)
        return [dummy]


class TrapStages(PipeModBaseChain):
    def get_chain(self):
        main = TrapMainStage(self.pspec)
        return [main]


class TrapBasePipe(ControlBase):
    def __init__(self, pspec):
        ControlBase.__init__(self)
        self.pspec = pspec
        self.pipe1 = TrapDummyStages(pspec)
        self.pipe2 = TrapStages(pspec)
        self._eqs = self.connect([self.pipe1, self.pipe2])

    def elaborate(self, platform):
        m = ControlBase.elaborate(self, platform)
        m.submodules.pipe1 = self.pipe1
        m.submodules.pipe2 = self.pipe2
        m.d.comb += self._eqs
        return m
