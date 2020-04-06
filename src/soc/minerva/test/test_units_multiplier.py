from nmigen import *
from nmigen.back.pysim import *
from nmigen.test.utils import *

from ..units.multiplier import *
from ..isa import Funct3


def tst_op(funct3, src1, src2, result):
    def test(self):
        with Simulator(self.dut) as sim:
            def process():
                yield self.dut.x_op.eq(funct3)
                yield self.dut.x_src1.eq(src1)
                yield self.dut.x_src2.eq(src2)
                yield self.dut.x_stall.eq(0)
                yield Tick()
                yield self.dut.m_stall.eq(0)
                yield Tick()
                yield Tick()
                self.assertEqual((yield self.dut.w_result), result)
            sim.add_clock(1e-6)
            sim.add_sync_process(process)
            sim.run()
    return test


class MultiplierTestCase(FHDLTestCase):
    def setUp(self):
        self.dut = Multiplier()

    # Test cases are taken from the riscv-compliance testbench:
    # https://github.com/riscv/riscv-compliance/tree/master/riscv-test-suite/rv32im

    # MUL ----------------------------------------------------------------------------

    test_mul_0 = tst_op(Funct3.MUL,    0x00000000,
                        0x00000000, result=0x00000000)
    test_mul_1 = tst_op(Funct3.MUL,    0x00000000,
                        0x00000001, result=0x00000000)
    test_mul_2 = tst_op(Funct3.MUL,    0x00000000,
                        0xffffffff, result=0x00000000)
    test_mul_3 = tst_op(Funct3.MUL,    0x00000000,
                        0x7fffffff, result=0x00000000)
    test_mul_4 = tst_op(Funct3.MUL,    0x00000000,
                        0x80000000, result=0x00000000)

    test_mul_5 = tst_op(Funct3.MUL,    0x00000001,
                        0x00000000, result=0x00000000)
    test_mul_6 = tst_op(Funct3.MUL,    0x00000001,
                        0x00000001, result=0x00000001)
    test_mul_7 = tst_op(Funct3.MUL,    0x00000001,
                        0xffffffff, result=0xffffffff)
    test_mul_8 = tst_op(Funct3.MUL,    0x00000001,
                        0x7fffffff, result=0x7fffffff)
    test_mul_9 = tst_op(Funct3.MUL,    0x00000001,
                        0x80000000, result=0x80000000)

    test_mul_10 = tst_op(Funct3.MUL,    0xffffffff,
                         0x00000000, result=0x00000000)
    test_mul_11 = tst_op(Funct3.MUL,    0xffffffff,
                         0x00000001, result=0xffffffff)
    test_mul_12 = tst_op(Funct3.MUL,    0xffffffff,
                         0xffffffff, result=0x00000001)
    test_mul_13 = tst_op(Funct3.MUL,    0xffffffff,
                         0x7fffffff, result=0x80000001)
    test_mul_14 = tst_op(Funct3.MUL,    0xffffffff,
                         0x80000000, result=0x80000000)

    test_mul_15 = tst_op(Funct3.MUL,    0x7fffffff,
                         0x00000000, result=0x00000000)
    test_mul_16 = tst_op(Funct3.MUL,    0x7fffffff,
                         0x00000001, result=0x7fffffff)
    test_mul_17 = tst_op(Funct3.MUL,    0x7fffffff,
                         0xffffffff, result=0x80000001)
    test_mul_18 = tst_op(Funct3.MUL,    0x7fffffff,
                         0x7fffffff, result=0x00000001)
    test_mul_19 = tst_op(Funct3.MUL,    0x7fffffff,
                         0x80000000, result=0x80000000)

    test_mul_20 = tst_op(Funct3.MUL,    0x80000000,
                         0x00000000, result=0x00000000)
    test_mul_21 = tst_op(Funct3.MUL,    0x80000000,
                         0x00000001, result=0x80000000)
    test_mul_22 = tst_op(Funct3.MUL,    0x80000000,
                         0xffffffff, result=0x80000000)
    test_mul_23 = tst_op(Funct3.MUL,    0x80000000,
                         0x7fffffff, result=0x80000000)
    test_mul_24 = tst_op(Funct3.MUL,    0x80000000,
                         0x80000000, result=0x00000000)

    # MULH ---------------------------------------------------------------------------

    test_mulh_0 = tst_op(Funct3.MULH,   0x00000000,
                         0x00000000, result=0x00000000)
    test_mulh_1 = tst_op(Funct3.MULH,   0x00000000,
                         0x00000001, result=0x00000000)
    test_mulh_2 = tst_op(Funct3.MULH,   0x00000000,
                         0xffffffff, result=0x00000000)
    test_mulh_3 = tst_op(Funct3.MULH,   0x00000000,
                         0x7fffffff, result=0x00000000)
    test_mulh_4 = tst_op(Funct3.MULH,   0x00000000,
                         0x80000000, result=0x00000000)

    test_mulh_5 = tst_op(Funct3.MULH,   0x00000001,
                         0x00000000, result=0x00000000)
    test_mulh_6 = tst_op(Funct3.MULH,   0x00000001,
                         0x00000001, result=0x00000000)
    test_mulh_7 = tst_op(Funct3.MULH,   0x00000001,
                         0xffffffff, result=0xffffffff)
    test_mulh_8 = tst_op(Funct3.MULH,   0x00000001,
                         0x7fffffff, result=0x00000000)
    test_mulh_9 = tst_op(Funct3.MULH,   0x00000001,
                         0x80000000, result=0xffffffff)

    test_mulh_10 = tst_op(Funct3.MULH,   0xffffffff,
                          0x00000000, result=0x00000000)
    test_mulh_11 = tst_op(Funct3.MULH,   0xffffffff,
                          0x00000001, result=0xffffffff)
    test_mulh_12 = tst_op(Funct3.MULH,   0xffffffff,
                          0xffffffff, result=0x00000000)
    test_mulh_13 = tst_op(Funct3.MULH,   0xffffffff,
                          0x7fffffff, result=0xffffffff)
    test_mulh_14 = tst_op(Funct3.MULH,   0xffffffff,
                          0x80000000, result=0x00000000)

    test_mulh_15 = tst_op(Funct3.MULH,   0x7fffffff,
                          0x00000000, result=0x00000000)
    test_mulh_16 = tst_op(Funct3.MULH,   0x7fffffff,
                          0x00000001, result=0x00000000)
    test_mulh_17 = tst_op(Funct3.MULH,   0x7fffffff,
                          0xffffffff, result=0xffffffff)
    test_mulh_18 = tst_op(Funct3.MULH,   0x7fffffff,
                          0x7fffffff, result=0x3fffffff)
    test_mulh_19 = tst_op(Funct3.MULH,   0x7fffffff,
                          0x80000000, result=0xc0000000)

    test_mulh_20 = tst_op(Funct3.MULH,   0x80000000,
                          0x00000000, result=0x00000000)
    test_mulh_21 = tst_op(Funct3.MULH,   0x80000000,
                          0x00000001, result=0xffffffff)
    test_mulh_22 = tst_op(Funct3.MULH,   0x80000000,
                          0xffffffff, result=0x00000000)
    test_mulh_23 = tst_op(Funct3.MULH,   0x80000000,
                          0x7fffffff, result=0xc0000000)
    test_mulh_24 = tst_op(Funct3.MULH,   0x80000000,
                          0x80000000, result=0x40000000)

    # MULHSU -------------------------------------------------------------------------

    test_mulhsu_0 = tst_op(Funct3.MULHSU, 0x00000000,
                           0x00000000, result=0x00000000)
    test_mulhsu_1 = tst_op(Funct3.MULHSU, 0x00000000,
                           0x00000001, result=0x00000000)
    test_mulhsu_2 = tst_op(Funct3.MULHSU, 0x00000000,
                           0xffffffff, result=0x00000000)
    test_mulhsu_3 = tst_op(Funct3.MULHSU, 0x00000000,
                           0x7fffffff, result=0x00000000)
    test_mulhsu_4 = tst_op(Funct3.MULHSU, 0x00000000,
                           0x80000000, result=0x00000000)

    test_mulhsu_5 = tst_op(Funct3.MULHSU, 0x00000001,
                           0x00000000, result=0x00000000)
    test_mulhsu_6 = tst_op(Funct3.MULHSU, 0x00000001,
                           0x00000001, result=0x00000000)
    test_mulhsu_7 = tst_op(Funct3.MULHSU, 0x00000001,
                           0xffffffff, result=0x00000000)
    test_mulhsu_8 = tst_op(Funct3.MULHSU, 0x00000001,
                           0x7fffffff, result=0x00000000)
    test_mulhsu_9 = tst_op(Funct3.MULHSU, 0x00000001,
                           0x80000000, result=0x00000000)

    test_mulhsu_10 = tst_op(Funct3.MULHSU, 0xffffffff,
                            0x00000000, result=0x00000000)
    test_mulhsu_11 = tst_op(Funct3.MULHSU, 0xffffffff,
                            0x00000001, result=0xffffffff)
    test_mulhsu_12 = tst_op(Funct3.MULHSU, 0xffffffff,
                            0xffffffff, result=0xffffffff)
    test_mulhsu_13 = tst_op(Funct3.MULHSU, 0xffffffff,
                            0x7fffffff, result=0xffffffff)
    test_mulhsu_14 = tst_op(Funct3.MULHSU, 0xffffffff,
                            0x80000000, result=0xffffffff)

    test_mulhsu_15 = tst_op(Funct3.MULHSU, 0x7fffffff,
                            0x00000000, result=0x00000000)
    test_mulhsu_16 = tst_op(Funct3.MULHSU, 0x7fffffff,
                            0x00000001, result=0x00000000)
    test_mulhsu_17 = tst_op(Funct3.MULHSU, 0x7fffffff,
                            0xffffffff, result=0x7ffffffe)
    test_mulhsu_18 = tst_op(Funct3.MULHSU, 0x7fffffff,
                            0x7fffffff, result=0x3fffffff)
    test_mulhsu_19 = tst_op(Funct3.MULHSU, 0x7fffffff,
                            0x80000000, result=0x3fffffff)

    test_mulhsu_20 = tst_op(Funct3.MULHSU, 0x80000000,
                            0x00000000, result=0x00000000)
    test_mulhsu_21 = tst_op(Funct3.MULHSU, 0x80000000,
                            0x00000001, result=0xffffffff)
    test_mulhsu_22 = tst_op(Funct3.MULHSU, 0x80000000,
                            0xffffffff, result=0x80000000)
    test_mulhsu_23 = tst_op(Funct3.MULHSU, 0x80000000,
                            0x7fffffff, result=0xc0000000)
    test_mulhsu_24 = tst_op(Funct3.MULHSU, 0x80000000,
                            0x80000000, result=0xc0000000)

    # MULHU --------------------------------------------------------------------------

    test_mulhu_0 = tst_op(Funct3.MULHU,  0x00000000,
                          0x00000000, result=0x00000000)
    test_mulhu_1 = tst_op(Funct3.MULHU,  0x00000000,
                          0x00000001, result=0x00000000)
    test_mulhu_2 = tst_op(Funct3.MULHU,  0x00000000,
                          0xffffffff, result=0x00000000)
    test_mulhu_3 = tst_op(Funct3.MULHU,  0x00000000,
                          0x7fffffff, result=0x00000000)
    test_mulhu_4 = tst_op(Funct3.MULHU,  0x00000000,
                          0x80000000, result=0x00000000)

    test_mulhu_5 = tst_op(Funct3.MULHU,  0x00000001,
                          0x00000000, result=0x00000000)
    test_mulhu_6 = tst_op(Funct3.MULHU,  0x00000001,
                          0x00000001, result=0x00000000)
    test_mulhu_7 = tst_op(Funct3.MULHU,  0x00000001,
                          0xffffffff, result=0x00000000)
    test_mulhu_8 = tst_op(Funct3.MULHU,  0x00000001,
                          0x7fffffff, result=0x00000000)
    test_mulhu_9 = tst_op(Funct3.MULHU,  0x00000001,
                          0x80000000, result=0x00000000)

    test_mulhu_10 = tst_op(Funct3.MULHU,  0xffffffff,
                           0x00000000, result=0x00000000)
    test_mulhu_11 = tst_op(Funct3.MULHU,  0xffffffff,
                           0x00000001, result=0x00000000)
    test_mulhu_12 = tst_op(Funct3.MULHU,  0xffffffff,
                           0xffffffff, result=0xfffffffe)
    test_mulhu_13 = tst_op(Funct3.MULHU,  0xffffffff,
                           0x7fffffff, result=0x7ffffffe)
    test_mulhu_14 = tst_op(Funct3.MULHU,  0xffffffff,
                           0x80000000, result=0x7fffffff)

    test_mulhu_15 = tst_op(Funct3.MULHU,  0x7fffffff,
                           0x00000000, result=0x00000000)
    test_mulhu_16 = tst_op(Funct3.MULHU,  0x7fffffff,
                           0x00000001, result=0x00000000)
    test_mulhu_17 = tst_op(Funct3.MULHU,  0x7fffffff,
                           0xffffffff, result=0x7ffffffe)
    test_mulhu_18 = tst_op(Funct3.MULHU,  0x7fffffff,
                           0x7fffffff, result=0x3fffffff)
    test_mulhu_19 = tst_op(Funct3.MULHU,  0x7fffffff,
                           0x80000000, result=0x3fffffff)

    test_mulhu_20 = tst_op(Funct3.MULHU,  0x80000000,
                           0x00000000, result=0x00000000)
    test_mulhu_21 = tst_op(Funct3.MULHU,  0x80000000,
                           0x00000001, result=0x00000000)
    test_mulhu_22 = tst_op(Funct3.MULHU,  0x80000000,
                           0xffffffff, result=0x7fffffff)
    test_mulhu_23 = tst_op(Funct3.MULHU,  0x80000000,
                           0x7fffffff, result=0x3fffffff)
    test_mulhu_24 = tst_op(Funct3.MULHU,  0x80000000,
                           0x80000000, result=0x40000000)
