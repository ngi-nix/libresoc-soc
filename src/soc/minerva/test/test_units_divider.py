from nmigen import *
from nmigen.back.pysim import *
from nmigen.test.utils import *

from ..units.divider import *
from ..isa import Funct3


def tst_op(funct3, src1, src2, result):
    def test(self):
        with Simulator(self.dut) as sim:
            def process():
                yield self.dut.x_op.eq(funct3)
                yield self.dut.x_src1.eq(src1)
                yield self.dut.x_src2.eq(src2)
                yield self.dut.x_valid.eq(1)
                yield self.dut.x_stall.eq(0)
                yield Tick()
                yield self.dut.x_valid.eq(0)
                yield Tick()
                while (yield self.dut.m_busy):
                    yield Tick()
                self.assertEqual((yield self.dut.m_result), result)
            sim.add_clock(1e-6)
            sim.add_sync_process(process)
            sim.run()
    return test


class DividerTestCase(FHDLTestCase):
    def setUp(self):
        self.dut = Divider()

    # Test cases are taken from the riscv-compliance testbench:
    # https://github.com/riscv/riscv-compliance/tree/master/riscv-test-suite/rv32im

    # DIV ------------------------------------------------------------------------

    test_div_0 = tst_op(Funct3.DIV,  0x00000000, 0x00000000, result=0xffffffff)
    test_div_1 = tst_op(Funct3.DIV,  0x00000000, 0x00000001, result=0x00000000)
    test_div_2 = tst_op(Funct3.DIV,  0x00000000, 0xffffffff, result=0x00000000)
    test_div_3 = tst_op(Funct3.DIV,  0x00000000, 0x7fffffff, result=0x00000000)
    test_div_4 = tst_op(Funct3.DIV,  0x00000000, 0x80000000, result=0x00000000)

    test_div_5 = tst_op(Funct3.DIV,  0x00000001, 0x00000000, result=0xffffffff)
    test_div_6 = tst_op(Funct3.DIV,  0x00000001, 0x00000001, result=0x00000001)
    test_div_7 = tst_op(Funct3.DIV,  0x00000001, 0xffffffff, result=0xffffffff)
    test_div_8 = tst_op(Funct3.DIV,  0x00000001, 0x7fffffff, result=0x00000000)
    test_div_9 = tst_op(Funct3.DIV,  0x00000001, 0x80000000, result=0x00000000)

    test_div_10 = tst_op(Funct3.DIV,  0xffffffff,
                         0x00000000, result=0xffffffff)
    test_div_11 = tst_op(Funct3.DIV,  0xffffffff,
                         0x00000001, result=0xffffffff)
    test_div_12 = tst_op(Funct3.DIV,  0xffffffff,
                         0xffffffff, result=0x00000001)
    test_div_13 = tst_op(Funct3.DIV,  0xffffffff,
                         0x7fffffff, result=0x00000000)
    test_div_14 = tst_op(Funct3.DIV,  0xffffffff,
                         0x80000000, result=0x00000000)

    test_div_15 = tst_op(Funct3.DIV,  0x7fffffff,
                         0x00000000, result=0xffffffff)
    test_div_16 = tst_op(Funct3.DIV,  0x7fffffff,
                         0x00000001, result=0x7fffffff)
    test_div_17 = tst_op(Funct3.DIV,  0x7fffffff,
                         0xffffffff, result=0x80000001)
    test_div_18 = tst_op(Funct3.DIV,  0x7fffffff,
                         0x7fffffff, result=0x00000001)
    test_div_19 = tst_op(Funct3.DIV,  0x7fffffff,
                         0x80000000, result=0x00000000)

    test_div_20 = tst_op(Funct3.DIV,  0x80000000,
                         0x00000000, result=0xffffffff)
    test_div_21 = tst_op(Funct3.DIV,  0x80000000,
                         0x00000001, result=0x80000000)
    test_div_22 = tst_op(Funct3.DIV,  0x80000000,
                         0xffffffff, result=0x80000000)
    test_div_23 = tst_op(Funct3.DIV,  0x80000000,
                         0x7fffffff, result=0xffffffff)
    test_div_24 = tst_op(Funct3.DIV,  0x80000000,
                         0x80000000, result=0x00000001)

    # DIVU -----------------------------------------------------------------------

    test_divu_0 = tst_op(Funct3.DIVU, 0x00000000,
                         0x00000000, result=0xffffffff)
    test_divu_1 = tst_op(Funct3.DIVU, 0x00000000,
                         0x00000001, result=0x00000000)
    test_divu_2 = tst_op(Funct3.DIVU, 0x00000000,
                         0xffffffff, result=0x00000000)
    test_divu_3 = tst_op(Funct3.DIVU, 0x00000000,
                         0x7fffffff, result=0x00000000)
    test_divu_4 = tst_op(Funct3.DIVU, 0x00000000,
                         0x80000000, result=0x00000000)

    test_divu_5 = tst_op(Funct3.DIVU, 0x00000001,
                         0x00000000, result=0xffffffff)
    test_divu_6 = tst_op(Funct3.DIVU, 0x00000001,
                         0x00000001, result=0x00000001)
    test_divu_7 = tst_op(Funct3.DIVU, 0x00000001,
                         0xffffffff, result=0x00000000)
    test_divu_8 = tst_op(Funct3.DIVU, 0x00000001,
                         0x7fffffff, result=0x00000000)
    test_divu_9 = tst_op(Funct3.DIVU, 0x00000001,
                         0x80000000, result=0x00000000)

    test_divu_10 = tst_op(Funct3.DIVU, 0xffffffff,
                          0x00000000, result=0xffffffff)
    test_divu_11 = tst_op(Funct3.DIVU, 0xffffffff,
                          0x00000001, result=0xffffffff)
    test_divu_12 = tst_op(Funct3.DIVU, 0xffffffff,
                          0xffffffff, result=0x00000001)
    test_divu_13 = tst_op(Funct3.DIVU, 0xffffffff,
                          0x7fffffff, result=0x00000002)
    test_divu_14 = tst_op(Funct3.DIVU, 0xffffffff,
                          0x80000000, result=0x00000001)

    test_divu_15 = tst_op(Funct3.DIVU, 0x7fffffff,
                          0x00000000, result=0xffffffff)
    test_divu_16 = tst_op(Funct3.DIVU, 0x7fffffff,
                          0x00000001, result=0x7fffffff)
    test_divu_17 = tst_op(Funct3.DIVU, 0x7fffffff,
                          0xffffffff, result=0x00000000)
    test_divu_18 = tst_op(Funct3.DIVU, 0x7fffffff,
                          0x7fffffff, result=0x00000001)
    test_divu_19 = tst_op(Funct3.DIVU, 0x7fffffff,
                          0x80000000, result=0x00000000)

    test_divu_20 = tst_op(Funct3.DIVU, 0x80000000,
                          0x00000000, result=0xffffffff)
    test_divu_21 = tst_op(Funct3.DIVU, 0x80000000,
                          0x00000001, result=0x80000000)
    test_divu_22 = tst_op(Funct3.DIVU, 0x80000000,
                          0xffffffff, result=0x00000000)
    test_divu_23 = tst_op(Funct3.DIVU, 0x80000000,
                          0x7fffffff, result=0x00000001)
    test_divu_24 = tst_op(Funct3.DIVU, 0x80000000,
                          0x80000000, result=0x00000001)

    # REM ------------------------------------------------------------------------

    test_rem_0 = tst_op(Funct3.REM,  0x00000000, 0x00000000, result=0x00000000)
    test_rem_1 = tst_op(Funct3.REM,  0x00000000, 0x00000001, result=0x00000000)
    test_rem_2 = tst_op(Funct3.REM,  0x00000000, 0xffffffff, result=0x00000000)
    test_rem_3 = tst_op(Funct3.REM,  0x00000000, 0x7fffffff, result=0x00000000)
    test_rem_4 = tst_op(Funct3.REM,  0x00000000, 0x80000000, result=0x00000000)

    test_rem_5 = tst_op(Funct3.REM,  0x00000001, 0x00000000, result=0x00000001)
    test_rem_6 = tst_op(Funct3.REM,  0x00000001, 0x00000001, result=0x00000000)
    test_rem_7 = tst_op(Funct3.REM,  0x00000001, 0xffffffff, result=0x00000000)
    test_rem_8 = tst_op(Funct3.REM,  0x00000001, 0x7fffffff, result=0x00000001)
    test_rem_9 = tst_op(Funct3.REM,  0x00000001, 0x80000000, result=0x00000001)

    test_rem_10 = tst_op(Funct3.REM,  0xffffffff,
                         0x00000000, result=0xffffffff)
    test_rem_11 = tst_op(Funct3.REM,  0xffffffff,
                         0x00000001, result=0x00000000)
    test_rem_12 = tst_op(Funct3.REM,  0xffffffff,
                         0xffffffff, result=0x00000000)
    test_rem_13 = tst_op(Funct3.REM,  0xffffffff,
                         0x7fffffff, result=0xffffffff)
    test_rem_14 = tst_op(Funct3.REM,  0xffffffff,
                         0x80000000, result=0xffffffff)

    test_rem_15 = tst_op(Funct3.REM,  0x7fffffff,
                         0x00000000, result=0x7fffffff)
    test_rem_16 = tst_op(Funct3.REM,  0x7fffffff,
                         0x00000001, result=0x00000000)
    test_rem_17 = tst_op(Funct3.REM,  0x7fffffff,
                         0xffffffff, result=0x00000000)
    test_rem_18 = tst_op(Funct3.REM,  0x7fffffff,
                         0x7fffffff, result=0x00000000)
    test_rem_19 = tst_op(Funct3.REM,  0x7fffffff,
                         0x80000000, result=0x7fffffff)

    test_rem_20 = tst_op(Funct3.REM,  0x80000000,
                         0x00000000, result=0x80000000)
    test_rem_21 = tst_op(Funct3.REM,  0x80000000,
                         0x00000001, result=0x00000000)
    test_rem_22 = tst_op(Funct3.REM,  0x80000000,
                         0xffffffff, result=0x00000000)
    test_rem_23 = tst_op(Funct3.REM,  0x80000000,
                         0x7fffffff, result=0xffffffff)
    test_rem_24 = tst_op(Funct3.REM,  0x80000000,
                         0x80000000, result=0x00000000)

    # REMU -----------------------------------------------------------------------

    test_remu_0 = tst_op(Funct3.REMU, 0x00000000,
                         0x00000000, result=0x00000000)
    test_remu_1 = tst_op(Funct3.REMU, 0x00000000,
                         0x00000001, result=0x00000000)
    test_remu_2 = tst_op(Funct3.REMU, 0x00000000,
                         0xffffffff, result=0x00000000)
    test_remu_3 = tst_op(Funct3.REMU, 0x00000000,
                         0x7fffffff, result=0x00000000)
    test_remu_4 = tst_op(Funct3.REMU, 0x00000000,
                         0x80000000, result=0x00000000)

    test_remu_5 = tst_op(Funct3.REMU, 0x00000001,
                         0x00000000, result=0x00000001)
    test_remu_6 = tst_op(Funct3.REMU, 0x00000001,
                         0x00000001, result=0x00000000)
    test_remu_7 = tst_op(Funct3.REMU, 0x00000001,
                         0xffffffff, result=0x00000001)
    test_remu_8 = tst_op(Funct3.REMU, 0x00000001,
                         0x7fffffff, result=0x00000001)
    test_remu_9 = tst_op(Funct3.REMU, 0x00000001,
                         0x80000000, result=0x00000001)

    test_remu_10 = tst_op(Funct3.REMU, 0xffffffff,
                          0x00000000, result=0xffffffff)
    test_remu_11 = tst_op(Funct3.REMU, 0xffffffff,
                          0x00000001, result=0x00000000)
    test_remu_12 = tst_op(Funct3.REMU, 0xffffffff,
                          0xffffffff, result=0x00000000)
    test_remu_13 = tst_op(Funct3.REMU, 0xffffffff,
                          0x7fffffff, result=0x00000001)
    test_remu_14 = tst_op(Funct3.REMU, 0xffffffff,
                          0x80000000, result=0x7fffffff)

    test_remu_15 = tst_op(Funct3.REMU, 0x7fffffff,
                          0x00000000, result=0x7fffffff)
    test_remu_16 = tst_op(Funct3.REMU, 0x7fffffff,
                          0x00000001, result=0x00000000)
    test_remu_17 = tst_op(Funct3.REMU, 0x7fffffff,
                          0xffffffff, result=0x7fffffff)
    test_remu_18 = tst_op(Funct3.REMU, 0x7fffffff,
                          0x7fffffff, result=0x00000000)
    test_remu_19 = tst_op(Funct3.REMU, 0x7fffffff,
                          0x80000000, result=0x7fffffff)

    test_remu_20 = tst_op(Funct3.REMU, 0x80000000,
                          0x00000000, result=0x80000000)
    test_remu_21 = tst_op(Funct3.REMU, 0x80000000,
                          0x00000001, result=0x00000000)
    test_remu_22 = tst_op(Funct3.REMU, 0x80000000,
                          0xffffffff, result=0x80000000)
    test_remu_23 = tst_op(Funct3.REMU, 0x80000000,
                          0x7fffffff, result=0x00000001)
    test_remu_24 = tst_op(Funct3.REMU, 0x80000000,
                          0x80000000, result=0x00000000)
