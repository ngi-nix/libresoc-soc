import tracemalloc

tracemalloc.start()

from nmigen.compat.sim import run_simulation

from TLB.TLB import TLB

from TestUtil.test_helper import assert_op

def tbench(dut):
    pass

def test_tlb():
    #FIXME UnusedElaboratable when the following line is uncommented
    #dut = TLB(15,36,64,8)
    #run_simulation(dut, tbench(dut), vcd_name="Waveforms/test_tlb.vcd")
    print("TLB Unit Test TODO")

if __name__ == "__main__":
    test_tlb()
