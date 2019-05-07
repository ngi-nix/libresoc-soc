import sys
sys.path.append("../src")
sys.path.append("../../TestUtil")

from nmigen.compat.sim import run_simulation

from LFSR import LFSR

from test_helper import assert_eq, assert_ne, assert_op

def testbench(dut):
    yield dut.enable.eq(1)
    yield dut.o.eq(9)
    yield
    yield
    yield
    yield
    yield
    yield
    yield
    yield
    yield
    yield
    yield
    yield

if __name__ == "__main__":
    dut = LFSR()
    run_simulation(dut, testbench(dut), vcd_name="Waveforms/test_lfsr.vcd")
    print("LFSR Unit Test Success")