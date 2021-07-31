"""
test cases for LDSTSplitter and L0CacheBuffer2
"""

from soc.experiment.l0_cache import L0CacheBuffer2
from nmigen import Module, Signal, Mux, Elaboratable, Cat, Const
from nmigen.cli import rtlil
from soc.scoreboard.addr_split import LDSTSplitter
from soc.scoreboard.addr_match import LenExpand

from soc.config.test.test_pi2ls import pi_ld, pi_st, pi_ldst

from soc.experiment.pimem import PortInterfaceBase

from nmigen.compat.sim import run_simulation, Settle

class TestCachedMemoryPortInterface(PortInterfaceBase):
    """TestCacheMemoryPortInterface

    This is a test class for simple verification of LDSTSplitter
    conforming to PortInterface
    """

    def __init__(self, regwid=64, addrwid=4):
        super().__init__(regwid, addrwid)
        self.ldst = LDSTSplitter(32, 48, 4)

    def set_wr_addr(self, m, addr, mask, misalign, msr_pr):
        m.d.comb += self.ldst.addr_i.eq(addr)

    def set_rd_addr(self, m, addr, mask, misalign, msr_pr):
        m.d.comb += self.ldst.addr_i.eq(addr)

    def set_wr_data(self, m, data, wen):
        m.d.comb += self.ldst.st_data_i.data.eq(data)  # write st to mem
        m.d.comb += self.ldst.is_st_i.eq(wen)  # enable writes
        st_ok = Const(1, 1)
        return st_ok

    def get_rd_data(self, m):
        # this path is still untested
        ld_ok = Const(1, 1)
        return self.ldst.ld_data_o.data, ld_ok

    def elaborate(self, platform):
        m = super().elaborate(platform)

        # add TestMemory as submodule
        m.submodules.ldst = self.ldst

        return m

    def ports(self):
        yield from super().ports()
        # TODO: memory ports


def tst_cache_single_run(dut):
    #test single byte
    addr = 0
    data = 0xfeedface
    yield from pi_st(dut.pi, addr, data, 1)

def test_cache_single():
    dut = TestCachedMemoryPortInterface()
    #LDSTSplitter(8, 48, 4) #data leng in bytes, address bits, select bits

    run_simulation(dut, tst_cache_single_run(dut),
                   vcd_name='test_cache_single.vcd')


if __name__ == '__main__':
    test_cache_single()
