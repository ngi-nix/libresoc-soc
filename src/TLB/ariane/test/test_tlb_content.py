import sys
sys.path.append("../src")
sys.path.append("../../../TestUtil")

from nmigen.compat.sim import run_simulation

from TLB.ariane.tlb_content import TLBContent

#def set_vaddr(addr):
#    yield dut.lu_vaddr_i.eq(addr)
#    yield dut.update_i.vpn.eq(addr>>12)

def tbench(dut):
    yield
    yield
    yield

if __name__ == "__main__":
    dut = TLBContent(4,4)
    #
    run_simulation(dut, tbench(dut), vcd_name="test_tlb_content.vcd")
    print("TLBContent Unit Test Success")
