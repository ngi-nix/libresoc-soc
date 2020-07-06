from nmutil.singlepipe import ControlBase
from nmutil.pipemodbase import PipeModBaseChain
from soc.fu.alu.input_stage import ALUInputStage
from soc.fu.alu.output_stage import ALUOutputStage
from soc.fu.mul.pre_stage import MulMainStage1
from soc.fu.mul.main_stage import MulMainStage2
from soc.fu.mul.post_stage import MulMainStage3


class MulStages1(PipeModBaseChain):
    def get_chain(self):
        inp = ALUInputStage(self.pspec)   # a-invert, carry etc
        main = MulMainStage1(self.pspec)  # detect signed/32-bit
        return [inp, main]


class MulStages2(PipeModBaseChain):
    def get_chain(self):
        main2 = MulMainStage2(self.pspec) # actual multiply
        return [main2]


class MulStages3(PipeModBaseChain):
    def get_chain(self):
        main3 = MulMainStage3(self.pspec) # select output bits, invert, set ov
        out = ALUOutputStage(self.pspec)  # do CR, XER and out-invert etc.
        return [main3, out]


class MulBasePipe(ControlBase):
    def __init__(self, pspec):
        ControlBase.__init__(self)
        self.pspec = pspec
        self.pipe1 = MulStages1(pspec)
        self.pipe2 = MulStages2(pspec)
        self.pipe3 = MulStages3(pspec)
        self._eqs = self.connect([self.pipe1, self.pipe2, self.pipe3])

    def elaborate(self, platform):
        m = ControlBase.elaborate(self, platform)
        m.submodules.mul_pipe1 = self.pipe1
        m.submodules.mul_pipe2 = self.pipe2
        m.submodules.mul_pipe3 = self.pipe3
        m.d.comb += self._eqs
        return m
