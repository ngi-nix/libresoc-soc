from nmigen.compat.sim import run_simulation

from tlb import TLB


def testbench(dut):
    yield dut.lu_access_i.eq(1)
    yield dut.lu_asid_i.eq(1)
    yield dut.lu_vaddr_i.eq(0x80000)
    yield dut.update_i.valid.eq(1)
    yield dut.update_i.is_1G.eq(0)
    yield dut.update_i.is_2M.eq(0)
    yield dut.update_i.vpn.eq(0x80000)
    yield dut.update_i.asid.eq(1)
    yield dut.update_i.content.ppn.eq(0)
    yield dut.update_i.content.rsw.eq(0)
    yield dut.update_i.content.r.eq(1)

    yield

    yield dut.lu_vaddr_i.eq(0x80000)
    yield dut.update_i.vpn.eq(0x80000)
    yield

    yield dut.lu_vaddr_i.eq(0x280000)
    yield dut.update_i.vpn.eq(0x280000)
    yield

    yield dut.lu_vaddr_i.eq(0x040000)
    yield dut.update_i.vpn.eq(0x040000)
    yield
    

if __name__ == "__main__":
    dut = TLB()
    run_simulation(dut, testbench(dut), vcd_name="test_tlb.vcd")
