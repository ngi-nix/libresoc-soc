# Proof of correctness for partitioned equal signal combiner
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>

from nmigen import (Module, Signal, Elaboratable, Mux, Cat, Repl,
                    signed)
from nmigen.asserts import Assert, AnyConst, Assume, Cover
from nmutil.formaltest import FHDLTestCase
from nmutil.stageapi import StageChain
from nmigen.cli import rtlil

from soc.fu.mul.pipe_data import CompMULOpSubset, MulPipeSpec
from soc.fu.mul.pre_stage import MulMainStage1
from soc.fu.mul.main_stage import MulMainStage2
from soc.fu.mul.post_stage import MulMainStage3

from soc.decoder.power_enums import MicrOp
import unittest


# This defines a module to drive the device under test and assert
# properties about its outputs
class Driver(Elaboratable):
    def __init__(self):
        # inputs and outputs
        pass

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        rec = CompMULOpSubset()

        # Setup random inputs for dut.op
        comb += rec.insn_type.eq(AnyConst(rec.insn_type.width))
        comb += rec.fn_unit.eq(AnyConst(rec.fn_unit.width))
        comb += rec.is_signed.eq(AnyConst(rec.is_signed.width))
        comb += rec.is_32bit.eq(AnyConst(rec.is_32bit.width))
        comb += rec.imm_data.imm.eq(AnyConst(64))
        comb += rec.imm_data.imm_ok.eq(AnyConst(1))
        # TODO, the rest of these.  (the for-loop hides Assert-failures)

        # set up the mul stages.  do not add them to m.submodules, this
        # is handled by StageChain.setup().
        pspec = MulPipeSpec(id_wid=2)
        pipe1 = MulMainStage1(pspec)
        pipe2 = MulMainStage2(pspec)
        pipe3 = MulMainStage3(pspec)

        class Dummy: pass
        dut = Dummy() # make a class into which dut.i and dut.o can be dropped
        dut.i = pipe1.ispec()
        chain = [pipe1, pipe2, pipe3] # chain of 3 mul stages

        StageChain(chain).setup(m, dut.i) # input linked here, through chain
        dut.o = chain[-1].o # output is the last thing in the chain...

        # convenience variables
        a = dut.i.ra
        b = dut.i.rb
#       ra = dut.i.ra
#       carry_in = dut.i.xer_ca[0]
#       carry_in32 = dut.i.xer_ca[1]
#       so_in = dut.i.xer_so
#       carry_out = dut.o.xer_ca
#       o = dut.o.o

        # setup random inputs
        comb += [a.eq(AnyConst(64)),
                 b.eq(AnyConst(64)),
                ]

        comb += dut.i.ctx.op.eq(rec)

        # Assert that op gets copied from the input to output
        comb += Assert(dut.o.ctx.op == dut.i.ctx.op)
        comb += Assert(dut.o.ctx.muxid == dut.i.ctx.muxid)

        # Assert that XER_SO propagates through as well.
        # Doesn't mean that the ok signal is always set though.
        comb += Assert(dut.o.xer_so.data == dut.i.xer_so)


        # signed and signed/32 versions of input a
#       a_signed = Signal(signed(64))
#       a_signed_32 = Signal(signed(32))
#       comb += a_signed.eq(a)
#       comb += a_signed_32.eq(a[0:32])

        # main assertion of arithmetic operations
        with m.Switch(rec.insn_type):
            with m.Case(MicrOp.OP_MUL_H32):
                comb += Assume(rec.is_32bit) # OP_MUL_H32 is a 32-bit op

                # unsigned hi32 - mulhwu
                with m.If(~rec.is_signed):
                    expected_product = Signal(64)
                    expected_o = Signal(64)
                    comb += expected_product.eq(a[0:32] * b[0:32])
                    comb += expected_o.eq(Repl(expected_product[32:64], 2))
                    comb += Assert(dut.o.o.data[0:64] == expected_o)

                # signed hi32 - mulhw
                with m.Else():
                    pass


        return m


class MulTestCase(FHDLTestCase):
    def test_formal(self):
        module = Driver()
        self.assertFormal(module, mode="bmc", depth=2)
        self.assertFormal(module, mode="cover", depth=2)
    def test_ilang(self):
        dut = Driver()
        vl = rtlil.convert(dut, ports=[])
        with open("main_stage.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
