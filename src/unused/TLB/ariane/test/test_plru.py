import sys
from soc.TLB.ariane.plru import PLRU
from nmigen.compat.sim import run_simulation


def tbench(dut):
    yield


if __name__ == "__main__":
    dut = PLRU(4)
    run_simulation(dut, tbench(dut), vcd_name="test_plru.vcd")
    print("PLRU Unit Test Success")
