#import tracemalloc
# tracemalloc.start()

from nmigen.compat.sim import run_simulation

from soc.TLB.TLB import TLB

from soc.TestUtil.test_helper import assert_op, assert_eq

# self.supermode = Signal(1) # Supervisor Mode
# self.super_access = Signal(1) # Supervisor Access
# self.command = Signal(2) # 00=None, 01=Search, 10=Write L1, 11=Write L2
# self.xwr = Signal(3) # Execute, Write, Read
# self.mode = Signal(4) # 4 bits for access to Sv48 on Rv64
#self.address_L1 = Signal(range(L1_size))
# self.asid = Signal(asid_size) # Address Space IDentifier (ASID)
# self.vma = Signal(vma_size) # Virtual Memory Address (VMA)
# self.pte_in = Signal(pte_size) # To be saved Page Table Entry (PTE)
#
# self.hit = Signal(1) # Denotes if the VMA had a mapped PTE
# self.perm_valid = Signal(1) # Denotes if the permissions are correct
# self.pte_out = Signal(pte_size) # PTE that was mapped to by the VMA

COMMAND_READ = 1
COMMAND_WRITE_L1 = 2

# Checks the data state of the CAM entry
# Arguments:
#   dut: The CamEntry being tested
#   d (Data): The expected data
#   op (Operation): (0 => ==), (1 => !=)


def check_hit(dut, d):
    hit_d = yield dut.hit
    #assert_eq("hit", hit_d, d)


def tst_command(dut, cmd, xwr, cycles):
    yield dut.command.eq(cmd)
    yield dut.xwr.eq(xwr)
    for i in range(0, cycles):
        yield


def tst_write_L1(dut, vma, address_L1, asid, pte_in):
    yield dut.address_L1.eq(address_L1)
    yield dut.asid.eq(asid)
    yield dut.vma.eq(vma)
    yield dut.pte_in.eq(pte_in)
    yield from tst_command(dut, COMMAND_WRITE_L1, 7, 2)


def tst_search(dut, vma, found):
    yield dut.vma.eq(vma)
    yield from tst_command(dut, COMMAND_READ, 7, 1)
    yield from check_hit(dut, found)


def zero(dut):
    yield dut.supermode.eq(0)
    yield dut.super_access.eq(0)
    yield dut.mode.eq(0)
    yield dut.address_L1.eq(0)
    yield dut.asid.eq(0)
    yield dut.vma.eq(0)
    yield dut.pte_in.eq(0)


def tbench(dut):
    yield from zero(dut)
    yield dut.mode.eq(0xF)  # enable TLB
    # test hit
    yield from tst_write_L1(dut, 0xFEEDFACE, 0, 0xFFFF, 0xF0F0)
    yield from tst_search(dut, 0xFEEDFACE, 1)
    yield from tst_search(dut, 0xFACEFEED, 0)


def test_tlb():
    dut = TLB(15, 36, 64, 8)
    run_simulation(dut, tbench(dut), vcd_name="Waveforms/test_tlb.vcd")
    print("TLB Unit Test Success")


if __name__ == "__main__":
    test_tlb()
