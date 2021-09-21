# test case for LOAD / STORE Computation Unit using MMU

from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Mux, Cat, Elaboratable, Array, Repl
from nmigen.hdl.rec import Record, Layout

from nmutil.latch import SRLatch, latchregister
from nmutil.byterev import byte_reverse
from nmutil.extend import exts
from soc.fu.regspec import RegSpecAPI

from openpower.decoder.power_enums import MicrOp, Function, LDSTMode
from soc.fu.ldst.ldst_input_record import CompLDSTOpSubset
from openpower.decoder.power_decoder2 import Data
from openpower.consts import MSR

from soc.experiment.compalu_multi import go_record, CompUnitRecord
from soc.experiment.l0_cache import PortInterface
from soc.experiment.pimem import LDSTException
from soc.experiment.compldst_multi import LDSTCompUnit
from soc.config.test.test_loadstore import TestMemPspec

########################################

def dcbz(dut, src1, src2, src3, imm, imm_ok=True, update=False,
          byterev=True):
    print("DCBZ", src1, src2, src3, imm, imm_ok, update)
    yield dut.oper_i.insn_type.eq(MicrOp.OP_DCBZ)
    yield dut.oper_i.data_len.eq(2)  # half-word
    yield dut.oper_i.byte_reverse.eq(byterev)
    yield dut.src1_i.eq(src1)
    yield dut.src2_i.eq(src2)
    yield dut.src3_i.eq(src3)
    yield dut.oper_i.imm_data.data.eq(imm)
    yield dut.oper_i.imm_data.ok.eq(imm_ok)
    #FIXME: -- yield dut.oper_i.update.eq(update)
    yield dut.issue_i.eq(1)
    yield
    yield dut.issue_i.eq(0)

    if imm_ok:
        active_rel = 0b101
    else:
        active_rel = 0b111
     # wait for all active rel signals to come up
    # guess: bug is here
    #while True:
    #    rel = yield dut.rd.rel_o
    #    if rel == active_rel:
    #        break
    #    yield
    #yield dut.rd.go_i.eq(active_rel)
    #yield
    #yield dut.rd.go_i.eq(0)

    #yield from wait_for(dut.adr_rel_o, False, test1st=True)
    # yield from wait_for(dut.adr_rel_o)
    # yield dut.ad.go.eq(1)
    # yield
    # yield dut.ad.go.eq(0)

    #if update:
    #    yield from wait_for(dut.wr.rel_o[1])
    #    yield dut.wr.go.eq(0b10)
    #    yield
    #    addr = yield dut.addr_o
    #    print("addr", addr)
    #    yield dut.wr.go.eq(0)
    #else:
    #    addr = None

    # commented out for debugging
    #yield from wait_for(dut.sto_rel_o)
    #yield dut.go_st_i.eq(1)
    #yield
    #yield dut.go_st_i.eq(0)
    #yield from wait_for(dut.busy_o, False)
    # wait_for(dut.stwd_mem_o)
    #yield
    #return addr


def ldst_sim(dut):
    yield from dcbz(dut, 4, 0, 3, 2) # FIXME
    yield

########################################


class TestLDSTCompUnitMMU(LDSTCompUnit):

    def __init__(self, rwid, pspec):
        from soc.experiment.l0_cache import TstL0CacheBuffer
        self.l0 = l0 = TstL0CacheBuffer(pspec)
        pi = l0.l0.dports[0]
        LDSTCompUnit.__init__(self, pi, rwid, 4)

    def elaborate(self, platform):
        m = LDSTCompUnit.elaborate(self, platform)
        m.submodules.l0 = self.l0
        # link addr-go direct to rel
        m.d.comb += self.ad.go_i.eq(self.ad.rel_o)
        return m


def test_scoreboard_mmu():

    units = {}
    pspec = TestMemPspec(ldst_ifacetype='mmu_cache_wb',
                         imem_ifacetype='bare_wb',
                         addr_wid=48,
                         mask_wid=8,
                         reg_wid=64,
                         units=units)

    dut = TestLDSTCompUnitMMU(16,pspec)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_ldst_comp_mmu1.il", "w") as f:
        f.write(vl)

    run_simulation(dut, ldst_sim(dut), vcd_name='test_ldst_comp.vcd')

########################################
class TestLDSTCompUnitRegSpecMMU(LDSTCompUnit):

    def __init__(self, pspec):
        from soc.experiment.l0_cache import TstL0CacheBuffer
        from soc.fu.ldst.pipe_data import LDSTPipeSpec
        regspec = LDSTPipeSpec.regspec
        self.l0 = l0 = TstL0CacheBuffer(pspec)
        pi = l0.l0.dports[0]
        LDSTCompUnit.__init__(self, pi, regspec, 4)

    def elaborate(self, platform):
        m = LDSTCompUnit.elaborate(self, platform)
        m.submodules.l0 = self.l0
        # link addr-go direct to rel
        m.d.comb += self.ad.go_i.eq(self.ad.rel_o)
        return m


def test_scoreboard_regspec_mmu():

    units = {}
    pspec = TestMemPspec(ldst_ifacetype='mmu_cache_wb',
                         imem_ifacetype='bare_wb',
                         addr_wid=48,
                         mask_wid=8,
                         reg_wid=64,
                         units=units)

    dut = TestLDSTCompUnitRegSpecMMU(pspec)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_ldst_comp_mmu2.il", "w") as f:
        f.write(vl)

    run_simulation(dut, ldst_sim(dut), vcd_name='test_ldst_regspec.vcd')


if __name__ == '__main__':
    test_scoreboard_regspec_mmu()
    #only one test for now -- test_scoreboard_mmu()
