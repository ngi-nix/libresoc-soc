from nmigen.compat.sim import run_simulation
import sys
sys.path.append("../")
# sys.path.append("../../../TestUtil")
from slice_top import slice_top

def tbench(dut):
    yield


if __name__ == "__main__":
    dut = slice_top()
    run_simulation(dut, tbench(dut), vcd_name="test_slice_top.vcd")
    print("slice_top Unit Test Success")
