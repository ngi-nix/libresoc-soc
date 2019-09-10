import sys
sys.path.append("../src")
sys.path.append("../../../TestUtil")

from nmigen.compat.sim import run_simulation

from TLB.ariane.tlb_content import TLBContent

def update():
    yield dut.replace_en_i.eq(1)
    
def tbench(dut):
    yield dut.replace_en_i.eq(1)
    yield dut.update_i.valid.eq(1)
    yield dut.update_i.is_512G.eq(1)
    yield dut.update_i.vpn.eq(0xFFFFFFFF)
    yield
    yield
    

if __name__ == "__main__":
    dut = TLBContent(4,4)
    #
    run_simulation(dut, tbench(dut), vcd_name="test_tlb_content.vcd")
    print("TLBContent Unit Test Success")
