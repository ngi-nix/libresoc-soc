from soc.minerva.units.fetch import FetchUnitInterface
from nmigen import Signal, Module, Elaboratable, Mux
from soc.experiment.testmem import TestMemory
from nmigen.cli import rtlil


class TestMemFetchUnit(FetchUnitInterface, Elaboratable):

    def __init__(self, addr_wid=32, data_wid=32):
        super().__init__(addr_wid=addr_wid, data_wid=data_wid)
        # limit TestMemory to 2^6 entries of regwid size
        self.mem = TestMemory(self.data_wid, 6, readonly=True)

    def elaborate(self, platform):
        m = Module()
        regwid, addrwid = self.data_wid, self.addr_wid
        adr_lsb = self.adr_lsbs

        m.submodules.mem = mem = self.mem

        do_fetch = Signal()  # set when fetch while valid and not stalled
        m.d.comb += do_fetch.eq(self.a_valid_i & ~self.a_stall_i)

        # bit of a messy FSM that progresses from idle to in progress
        # to done.
        op_actioned = Signal(reset=0)
        op_in_progress = Signal(reset=0)
        with m.If(~op_actioned & do_fetch): # idle
            m.d.sync += op_actioned.eq(1)
            m.d.sync += op_in_progress.eq(1)
        with m.Elif(op_in_progress):                    # in progress
            m.d.sync += op_actioned.eq(0)
        with m.If(~do_fetch):               # done
            m.d.sync += op_in_progress.eq(0)

        m.d.comb += self.a_busy_o.eq(op_actioned & self.a_valid_i)
        # fetch
        m.d.comb += mem.rdport.addr.eq(self.a_pc_i[adr_lsb:])
        m.d.comb += self.f_instr_o.eq(mem.rdport.data)

        return m


if __name__ == '__main__':
    dut = TestMemFetchUnit(addr_wid=32, data_wid=32)
    vl = rtlil.convert(dut, ports=[]) # TODOdut.ports())
    with open("test_imem.il", "w") as f:
        f.write(vl)

