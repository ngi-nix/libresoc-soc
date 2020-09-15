from nmigen import Elaboratable, Module, Signal, Shape, unsigned, Cat, Mux
from soc.fu.mmu.pipe_data import MMUInputData, MMUOutputData, MMUPipeSpec
from nmutil.singlepipe import ControlBase


class FSMMMUStage(ControlBase):
    def __init__(self, pspec):
        super().__init__()
        self.pspec = pspec
        # set up p/n data
        self.p.data_i = MMUInputData(pspec)
        self.n.data_o = MMUOutputData(pspec)

    def elaborate(self, platform):
        m = super().elaborate(platform)
        data_i = self.p.data_i
        data_o = self.n.data_o

        m.d.comb += self.n.valid_o.eq(~self.empty & self.div_state_next.o.done)
        m.d.comb += self.p.ready_o.eq(self.empty)
        m.d.sync += self.saved_state.eq(self.div_state_next.o)

        with m.If(self.empty):
            with m.If(self.p.valid_i):
                m.d.sync += self.empty.eq(0)
                m.d.sync += self.saved_input_data.eq(data_i)
        with m.Else():
            m.d.comb += [
            with m.If(self.n.ready_i & self.n.valid_o):
                m.d.sync += self.empty.eq(1)

        return m

    def __iter__(self):
        yield from self.p
        yield from self.n

    def ports(self):
        return list(self)
