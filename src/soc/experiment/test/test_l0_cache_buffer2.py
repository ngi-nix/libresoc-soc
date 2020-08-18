"""
test cases for LDSTSplitter and L0CacheBuffer2
"""

from soc.experiment.l0_cache import L0CacheBuffer2
from nmigen import Module
from nmigen.cli import rtlil
from soc.scoreboard.addr_split import LDSTSplitter
from soc.scoreboard.addr_match import LenExpand

from soc.config.test.test_pi2ls import pi_ld, pi_st, pi_ldst

#cxxsim = False
#if cxxsim:
#    from nmigen.sim.cxxsim import Simulator, Settle
#else:
#    from nmigen.back.pysim import Simulator, Settle
from nmigen.compat.sim import run_simulation, Settle

def writeMulti(dut):
    for i in range(dut.n_units):
        yield dut.dports[i].is_st_i.eq(1)
        yield dut.dports[i].addr.data.eq(i)
    yield
    # TODO assert that outputs are valid

def test_cache_run(dut):
    yield from writeMulti(dut)

def test_cache_single_run(dut):
    #test single byte
    addr = 0
    data = 0xfeedface
    yield from pi_st(dut.pi, addr, data, 1)

def test_cache():
    dut = L0CacheBuffer2()

    #vl = rtlil.convert(dut, ports=dut.ports())
    #with open("test_data_merger.il", "w") as f:
    #    f.write(vl)

    run_simulation(dut, test_cache_run(dut),
                   vcd_name='test_cache.vcd')

def test_cache_single():
    dut = LDSTSplitter(8, 48, 4) #data leng in bytes, address bits, select bits

    run_simulation(dut, test_cache_single_run(dut),
                   vcd_name='test_cache_single.vcd')


if __name__ == '__main__':
    #test_cache()
    test_cache_single()
