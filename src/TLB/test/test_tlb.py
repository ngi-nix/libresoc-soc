#import tracemalloc
#tracemalloc.start()

from nmigen.compat.sim import run_simulation

from TLB.TLB import TLB

from TestUtil.test_helper import assert_op, assert_eq

#self.supermode = Signal(1) # Supervisor Mode
#self.super_access = Signal(1) # Supervisor Access
#self.command = Signal(2) # 00=None, 01=Search, 10=Write L1, 11=Write L2
#self.xwr = Signal(3) # Execute, Write, Read
#self.mode = Signal(4) # 4 bits for access to Sv48 on Rv64
#self.address_L1 = Signal(max=L1_size)
#self.asid = Signal(asid_size) # Address Space IDentifier (ASID)
#self.vma = Signal(vma_size) # Virtual Memory Address (VMA)
#self.pte_in = Signal(pte_size) # To be saved Page Table Entry (PTE)
#
#self.hit = Signal(1) # Denotes if the VMA had a mapped PTE
#self.perm_valid = Signal(1) # Denotes if the permissions are correct
#self.pte_out = Signal(pte_size) # PTE that was mapped to by the VMA

COMMAND_READ=1

# Checks the data state of the CAM entry
# Arguments:
#   dut: The CamEntry being tested
#   d (Data): The expected data
#   op (Operation): (0 => ==), (1 => !=)
def check_hit(dut, d):
    hit_d = yield dut.hit
    assert_eq("Data", hit_d, d)

def test_command(dut,cmd,xwr,cycles):
    yield dut.command.eq(cmd)
    yield dut.xwr.eq(xwr)
    for i in range(0,cycles):
        yield

def zero(dut):
    yield dut.supermode.eq(0)
    yield dut.super_access.eq(0)
    yield dut.mode.eq(0)
    yield dut.address_L1.eq(0)
    yield dut.asid.eq(0)
    yield dut.vma.eq(0)
    yield dut.pte_in.eq(0)

#TWO test cases: search, write_l1

def tbench(dut):
    #first set all signals to default values
    yield from zero(dut)
    yield from test_command(dut,COMMAND_READ,7,10)
    yield from check_hit(dut,0) #hit will be zero since there is no entry yet
    # TODO store an address
    

def test_tlb():
    dut = TLB(15,36,64,8)
    run_simulation(dut, tbench(dut), vcd_name="Waveforms/test_tlb.vcd")
    print("TLB Unit Test WIP")

if __name__ == "__main__":
    test_tlb()
