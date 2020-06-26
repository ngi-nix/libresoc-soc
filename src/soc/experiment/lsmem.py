from soc.minerva.units.loadstore import LoadStoreUnitInterface
from nmigen import Signal, Module, Elaboratable, Mux
from nmigen.utils import log2_int
from soc.experiment.testmem import TestMemory # TODO: replace with TMLSUI
from nmigen.cli import rtlil


class TestMemLoadStoreUnit(LoadStoreUnitInterface, Elaboratable):
    def __init__(self, addr_wid=32, mask_wid=4, data_wid=32):
        super().__init__()
        self.regwid = data_wid
        self.addrwid = addr_wid
        self.mask_wid = mask_wid

    def elaborate(self, platform):
        m = Module()
        regwid, addrwid, mask_wid = self.regwid, self.addrwid, self.mask_wid
        adr_lsb = self.adr_lsbs

        # limit TestMemory to 2^6 entries of regwid size
        m.submodules.mem = mem = TestMemory(regwid, 6, granularity=8)

        do_load = Signal()  # set when doing a load while valid and not stalled
        do_store = Signal() # set when doing a store while valid and not stalled

        m.d.comb += [
            do_load.eq(self.x_ld_i & (self.x_valid_i & ~self.x_stall_i)),
            do_store.eq(self.x_st_i & (self.x_valid_i & ~self.x_stall_i)),
            ]
        m.d.comb += [
            # load
            mem.rdport.addr.eq(self.x_addr_i[adr_lsb:]),
            self.m_ld_data_o.eq(mem.rdport.data),

            # store
            mem.wrport.addr.eq(self.x_addr_i[adr_lsb:]),
            mem.wrport.en.eq(Mux(do_store, self.x_mask_i, 0)),
            mem.wrport.data.eq(self.x_st_data_i)
            ]

        return m


if __name__ == '__main__':
    dut = TestMemLoadStoreUnit(regwid=32, addrwid=4)
    vl = rtlil.convert(dut, ports=[]) # TODOdut.ports())
    with open("test_lsmem.il", "w") as f:
        f.write(vl)

