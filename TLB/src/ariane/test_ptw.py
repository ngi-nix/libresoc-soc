from nmigen.compat.sim import run_simulation

from ptw import PTW, PTE


def testbench(dut):

    addr = 0x8000000

    #pte = PTE()
    #yield pte.v.eq(1)
    #yield pte.r.eq(1)

    yield dut.req_port_i.data_gnt.eq(1)
    yield dut.req_port_i.data_rvalid.eq(1)
    yield dut.req_port_i.data_rdata.eq(0xc2<<56)#pte.flatten())

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

    yield

    

if __name__ == "__main__":
    dut = PTW()
    run_simulation(dut, testbench(dut), vcd_name="test_ptw.vcd")
