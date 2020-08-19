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
        recwidth = 0
        for p in rec.ports():
            width = p.width
            recwidth += width
            comb += p.eq(AnyConst(width))

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

        # I don't know how to check instruction behavior without picking
        # apart individual stages and peeking inside what should be private
        # interfaces.  Otherwise, I'm just rewriting, line for line, the
        # logic that is already in the implementation code.
        stage2_inputs = pipe2.ispec()

        # convenience variables
#       a = dut.i.rs
#       b = dut.i.rb
#       ra = dut.i.ra
#       carry_in = dut.i.xer_ca[0]
#       carry_in32 = dut.i.xer_ca[1]
#       so_in = dut.i.xer_so
#       carry_out = dut.o.xer_ca
#       o = dut.o.o

        # setup random inputs
#       comb += [a.eq(AnyConst(64)),
#                b.eq(AnyConst(64)),
#                carry_in.eq(AnyConst(1)),
#                carry_in32.eq(AnyConst(1)),
#                so_in.eq(AnyConst(1))]

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

        intermediate_result = Signal(len(stage2_inputs.a) + len(stage2_inputs.b))
        comb += intermediate_result.eq(stage2_inputs.a * stage2_inputs.b)

        expected_product = Signal.like(intermediate_result)
        with m.If(stage2_inputs.neg_res):
            comb += expected_product.eq(-intermediate_result)
        with m.Else():
            comb += expected_product.eq(intermediate_result)

        # main assertion of arithmetic operations
        with m.Switch(rec.insn_type):
            with m.Case(MicrOp.OP_MUL_H32):
                comb += Assert(dut.o.o.data == Repl(expected_product[32:64], 2))

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
