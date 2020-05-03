from ram_tp_write_first import ram_tp_write_first
from nmigen.compat.sim import run_simulation
import sys
sys.path.append("../")


def tbench(dut):
    yield dut.we.eq(1)
    for i in range(0, 255):
        yield dut.addr0.eq(i)
        yield dut.d_i.eq(i)
        yield


if __name__ == "__main__":
    dut = ram_tp_write_first()
    run_simulation(dut, tbench(dut), vcd_name="ram_tp_write_first.vcd")
    print("ram_tp_write_first Unit Test Success")
