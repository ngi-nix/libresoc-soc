from nmigen.compat.sim import run_simulation

from soc.TLB.ariane.tlb import TLB


def set_vaddr(addr):
    yield dut.lu_vaddr_i.eq(addr)
    yield dut.update_i.vpn.eq(addr >> 12)


def tbench(dut):
    yield dut.lu_access_i.eq(1)
    yield dut.lu_asid_i.eq(1)
    yield dut.update_i.valid.eq(1)
    yield dut.update_i.is_1G.eq(0)
    yield dut.update_i.is_2M.eq(0)
    yield dut.update_i.asid.eq(1)
    yield dut.update_i.content.ppn.eq(0)
    yield dut.update_i.content.rsw.eq(0)
    yield dut.update_i.content.r.eq(1)

    yield

    addr = 0x80000
    yield from set_vaddr(addr)
    yield

    addr = 0x90001
    yield from set_vaddr(addr)
    yield

    addr = 0x28000000
    yield from set_vaddr(addr)
    yield

    addr = 0x28000001
    yield from set_vaddr(addr)

    addr = 0x28000001
    yield from set_vaddr(addr)
    yield

    addr = 0x1000040000
    yield from set_vaddr(addr)
    yield

    addr = 0x1000040001
    yield from set_vaddr(addr)
    yield

    yield dut.update_i.is_1G.eq(1)
    addr = 0x2040000
    yield from set_vaddr(addr)
    yield

    yield dut.update_i.is_1G.eq(1)
    addr = 0x2040001
    yield from set_vaddr(addr)
    yield

    yield


if __name__ == "__main__":
    dut = TLB()
    run_simulation(dut, tbench(dut), vcd_name="test_tlb.vcd")
    print("TLB Unit Test Success")
