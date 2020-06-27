from soc.minerva.units.loadstore import LoadStoreUnitInterface
from nmigen import Signal, Module, Elaboratable, Mux
from nmigen.utils import log2_int
from soc.experiment.testmem import TestMemory # TODO: replace with TMLSUI
from nmigen.cli import rtlil


class TestMemLoadStoreUnit(LoadStoreUnitInterface, Elaboratable):

    def elaborate(self, platform):
        m = Module()
        regwid, addrwid, mask_wid = self.data_wid, self.addr_wid, self.mask_wid
        adr_lsb = self.adr_lsbs

        # limit TestMemory to 2^6 entries of regwid size
        m.submodules.mem = mem = TestMemory(regwid, 6, granularity=8)

        do_load = Signal()  # set when load while valid and not stalled
        do_store = Signal() # set when store while valid and not stalled

        m.d.comb += [
            do_load.eq(self.x_ld_i & (self.x_valid_i & ~self.x_stall_i)),
            do_store.eq(self.x_st_i & (self.x_valid_i & ~self.x_stall_i)),
            ]
        # bit of a messy FSM that progresses from idle to in progress
        # to done.
        op_actioned = Signal(reset=0)
        op_in_progress = Signal(reset=0)
        with m.If(~op_actioned & (do_load | do_store)): # idle
            m.d.sync += op_actioned.eq(1)
            m.d.sync += op_in_progress.eq(1)
        with m.Elif(op_in_progress):                    # in progress
            m.d.sync += op_actioned.eq(0)
        with m.If(~(do_load | do_store)):               # done
            m.d.sync += op_in_progress.eq(0)

        m.d.comb += self.x_busy_o.eq(op_actioned & self.x_valid_i)

        m.d.comb += [
            # load
            mem.rdport.addr.eq(self.x_addr_i[adr_lsb:]),
            self.m_ld_data_o.eq(mem.rdport.data),

            # store - only activates once
            mem.wrport.addr.eq(self.x_addr_i[adr_lsb:]),
            mem.wrport.en.eq(Mux(do_store & ~op_actioned,
                                 self.x_mask_i, 0)),
            mem.wrport.data.eq(self.x_st_data_i)
            ]

        return m


if __name__ == '__main__':
    dut = TestMemLoadStoreUnit(regwid=32, addrwid=4)
    vl = rtlil.convert(dut, ports=[]) # TODOdut.ports())
    with open("test_lsmem.il", "w") as f:
        f.write(vl)

