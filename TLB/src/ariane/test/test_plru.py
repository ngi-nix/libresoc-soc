import sys
sys.path.append("../src")
sys.path.append("../../../TestUtil")

from plru import PLRU

from nmigen.compat.sim import run_simulation

def testbench(dut):
    yield

if __name__ == "__main__":
    dut = PLRU(4)
    run_simulation(dut, testbench(dut), vcd_name="test_plru.vcd")
    print("PLRU Unit Test Success")