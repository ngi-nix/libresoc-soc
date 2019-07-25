#import tracemalloc
#tracemalloc.start()

from nmigen.compat.sim import run_simulation

from TLB.TLB import TLB

from TestUtil.test_helper import assert_op

def tbench(dut):
    yield
    yield
    #TODO

def test_tlb():
    dut = TLB(15,36,64,8)
    run_simulation(dut, tbench(dut), vcd_name="Waveforms/test_tlb.vcd")
    print("TLB Unit Test TODO")

if __name__ == "__main__":
    test_tlb()
