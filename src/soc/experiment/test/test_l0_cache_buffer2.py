"""
TODO
"""

from soc.experiment.l0_cache import L0CacheBuffer2
from nmigen import Module
from nmigen.cli import rtlil
#cxxsim = False
#if cxxsim:
#    from nmigen.sim.cxxsim import Simulator, Settle
#else:
#    from nmigen.back.pysim import Simulator, Settle
from nmigen.compat.sim import run_simulation, Settle

def test_cache_run(dut):
    yield

def test_cache():
    dut = L0CacheBuffer2()

    #vl = rtlil.convert(dut, ports=dut.ports())
    # with open("test_data_merger.il", "w") as f:
    #    f.write(vl)

    run_simulation(dut, test_cache_run(dut),
                   vcd_name='test_cache.vcd')

if __name__ == '__main__':
    test_cache()
    #TODO make debug output optional
