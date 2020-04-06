from nmigen.compat.sim import run_simulation
from soc.TLB.ariane.ptw import PTW, PTE

# unit was changed, test needs to be changed


def tbench(dut):

    addr = 0x8000000

    #pte = PTE()
    # yield pte.v.eq(1)
    # yield pte.r.eq(1)

    yield dut.req_port_i.data_gnt.eq(1)
    yield dut.req_port_i.data_rvalid.eq(1)
    yield dut.req_port_i.data_rdata.eq(0x43)  # pte.flatten())

    # data lookup
    yield dut.en_ld_st_translation_i.eq(1)
    yield dut.asid_i.eq(1)

    yield dut.dtlb_access_i.eq(1)
    yield dut.dtlb_hit_i.eq(0)
    yield dut.dtlb_vaddr_i.eq(0x400000000)

    yield
    yield
    yield

    yield dut.dtlb_access_i.eq(1)
    yield dut.dtlb_hit_i.eq(0)
    yield dut.dtlb_vaddr_i.eq(0x200000)

    yield
    yield
    yield

    yield dut.req_port_i.data_gnt.eq(0)
    yield dut.dtlb_access_i.eq(1)
    yield dut.dtlb_hit_i.eq(0)
    yield dut.dtlb_vaddr_i.eq(0x400000011)

    yield
    yield dut.req_port_i.data_gnt.eq(1)
    yield
    yield

    # data lookup, PTW levels 1-2-3
    addr = 0x4000000
    yield dut.dtlb_vaddr_i.eq(addr)
    yield dut.mxr_i.eq(0x1)
    yield dut.req_port_i.data_gnt.eq(1)
    yield dut.req_port_i.data_rvalid.eq(1)
    # pte.flatten())
    yield dut.req_port_i.data_rdata.eq(0x41 | (addr >> 12) << 10)

    yield dut.en_ld_st_translation_i.eq(1)
    yield dut.asid_i.eq(1)

    yield dut.dtlb_access_i.eq(1)
    yield dut.dtlb_hit_i.eq(0)
    yield dut.dtlb_vaddr_i.eq(addr)

    yield
    yield
    yield
    yield
    yield
    yield
    yield
    yield

    yield dut.req_port_i.data_gnt.eq(0)
    yield dut.dtlb_access_i.eq(1)
    yield dut.dtlb_hit_i.eq(0)
    yield dut.dtlb_vaddr_i.eq(0x400000011)

    yield
    yield dut.req_port_i.data_gnt.eq(1)
    yield
    yield
    yield
    yield

    # instruction lookup
    yield dut.en_ld_st_translation_i.eq(0)
    yield dut.enable_translation_i.eq(1)
    yield dut.asid_i.eq(1)

    yield dut.itlb_access_i.eq(1)
    yield dut.itlb_hit_i.eq(0)
    yield dut.itlb_vaddr_i.eq(0x800000)

    yield
    yield
    yield

    yield dut.itlb_access_i.eq(1)
    yield dut.itlb_hit_i.eq(0)
    yield dut.itlb_vaddr_i.eq(0x200000)

    yield
    yield
    yield

    yield dut.req_port_i.data_gnt.eq(0)
    yield dut.itlb_access_i.eq(1)
    yield dut.itlb_hit_i.eq(0)
    yield dut.itlb_vaddr_i.eq(0x800011)

    yield
    yield dut.req_port_i.data_gnt.eq(1)
    yield
    yield

    yield


def test_ptw():
    dut = PTW()
    run_simulation(dut, tbench(dut), vcd_name="test_ptw.vcd")
    print("PTW Unit Test Success")


if __name__ == "__main__":
    test_ptw()
