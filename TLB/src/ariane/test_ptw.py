from nmigen.compat.sim import run_simulation

from ptw import PTW


def testbench(dut):
    yield dut.req_port_i.data_gnt.eq(1)
    yield dut.req_port_i.data_rvalid.eq(1)
    yield dut.req_port_i.data_rdata.eq(0x0001)

    yield dut.enable_translation_i.eq(1)
    yield dut.asid_i.eq(1)

    yield dut.itlb_access_i.eq(1)
    yield dut.itlb_hit_i.eq(0)
    yield dut.itlb_vaddr_i.eq(0x0001)

    yield
    yield
    yield
    yield

    

if __name__ == "__main__":
    dut = PTW()
    run_simulation(dut, testbench(dut), vcd_name="test_ptw.vcd")
