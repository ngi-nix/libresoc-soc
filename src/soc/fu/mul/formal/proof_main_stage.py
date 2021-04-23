# Proof of correctness for multiplier
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>
# Copyright (C) 2020 Luke Kenneth Casson Leighton <lkcl@lkcl.net>
# Copyright (C) 2020 Samuel A. Falvo II <kc5tja@arrl.net>

"""Formal Correctness Proof for POWER9 multiplier

notes for ov/32.  similar logic applies for 64-bit quantities (m63)

    m31 = exp_prod[31:64]
    comb += expected_ov.eq(m31.bool() & ~m31.all())

    If the instruction enables the OV and OV32 flags to be
    set, then we must set them both to 1 if and only if
    the resulting product *cannot* be contained within a
    32-bit quantity.

    This is detected by checking to see if the resulting
    upper bits are either all 1s or all 0s.  If even *one*
    bit in this set differs from its peers, then we know
    the signed value cannot be contained in the destination's
    field width.

    m31.bool() is true if *any* high bit is set.
    m31.all() is true if *all* high bits are set.

    m31.bool()  m31.all()  Meaning
        0           x      All upper bits are 0, so product
                           is positive.  Thus, it fits.
        1           0      At least *one* high bit is clear.
                           Implying, not all high bits are
                           clones of the output sign bit.
                           Thus, product extends beyond
                           destination register size.
        1           1      All high bits are set *and* they
                           match the sign bit.  The number
                           is properly negative, and fits
                           in the destination register width.

    Note that OV/OV32 are set to the *inverse* of m31.all(),
    hence the expression m31.bool() & ~m31.all().
"""


from nmigen import (Module, Signal, Elaboratable, Mux, Cat, Repl,
                    signed)
from nmigen.asserts import Assert, AnyConst, Assume, Cover
from nmutil.formaltest import FHDLTestCase
from nmutil.stageapi import StageChain
from nmigen.cli import rtlil

from openpower.decoder.power_fields import DecodeFields
from openpower.decoder.power_fieldsn import SignalBitRange

from soc.fu.mul.pipe_data import CompMULOpSubset, MulPipeSpec
from soc.fu.mul.pre_stage import MulMainStage1
from soc.fu.mul.main_stage import MulMainStage2
from soc.fu.mul.post_stage import MulMainStage3

from openpower.decoder.power_enums import MicrOp
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
        o = dut.o.o.data
        xer_ov_o = dut.o.xer_ov.data
        xer_ov_ok = dut.o.xer_ov.ok

        # For 32- and 64-bit parameters, work out the absolute values of the
        # input parameters for signed multiplies.  Needed for signed
        # multiplication.

        abs32_a = Signal(32)
        abs32_b = Signal(32)
        abs64_a = Signal(64)
        abs64_b = Signal(64)
        a32_s = Signal(1)
        b32_s = Signal(1)
        a64_s = Signal(1)
        b64_s = Signal(1)

        comb += a32_s.eq(a[31])
        comb += b32_s.eq(b[31])
        comb += a64_s.eq(a[63])
        comb += b64_s.eq(b[63])

        comb += abs32_a.eq(Mux(a32_s, -a[0:32], a[0:32]))
        comb += abs32_b.eq(Mux(b32_s, -b[0:32], b[0:32]))
        comb += abs64_a.eq(Mux(a64_s, -a[0:64], a[0:64]))
        comb += abs64_b.eq(Mux(b64_s, -b[0:64], b[0:64]))

        # For 32- and 64-bit quantities, break out whether signs differ.
        # (the _sne suffix is read as "signs not equal").
        #
        # This is required because of the rules of signed multiplication:
        #
        # a*b = +(abs(a)*abs(b)) for two positive numbers a and b.
        # a*b = -(abs(a)*abs(b)) for any one positive number and negative
        #                        number.
        # a*b = +(abs(a)*abs(b)) for two negative numbers a and b.

        ab32_sne = Signal()
        ab64_sne = Signal()
        comb += ab32_sne.eq(a32_s ^ b32_s)
        comb += ab64_sne.eq(a64_s ^ b64_s)

        # setup random inputs
        comb += [a.eq(AnyConst(64)),
                 b.eq(AnyConst(64)),
                ]

        comb += dut.i.ctx.op.eq(rec)

        # check overflow and result flags
        result_ok = Signal()
        enable_overflow = Signal()

        # default to 1, disabled if default case is hit
        comb += result_ok.eq(1)

        # Assert that op gets copied from the input to output
        comb += Assert(dut.o.ctx.op == dut.i.ctx.op)
        comb += Assert(dut.o.ctx.muxid == dut.i.ctx.muxid)

        # Assert that XER_SO propagates through as well.
        comb += Assert(dut.o.xer_so == dut.i.xer_so)

        # main assertion of arithmetic operations
        with m.Switch(rec.insn_type):

            ###### HI-32 #####

            with m.Case(MicrOp.OP_MUL_H32):
                comb += Assume(rec.is_32bit) # OP_MUL_H32 is a 32-bit op

                exp_prod = Signal(64)
                expected_o = Signal.like(exp_prod)

                # unsigned hi32 - mulhwu
                with m.If(~rec.is_signed):
                    comb += exp_prod.eq(a[0:32] * b[0:32])
                    comb += expected_o.eq(Repl(exp_prod[32:64], 2))
                    comb += Assert(o[0:64] == expected_o)

                # signed hi32 - mulhw
                with m.Else():
                    # Per rules of signed multiplication, if input signs
                    # differ, we negate the product.  This implies that
                    # the product is calculated from the absolute values
                    # of the inputs.
                    prod = Signal.like(exp_prod) # intermediate product
                    comb += prod.eq(abs32_a * abs32_b)
                    comb += exp_prod.eq(Mux(ab32_sne, -prod, prod))
                    comb += expected_o.eq(Repl(exp_prod[32:64], 2))
                    comb += Assert(o[0:64] == expected_o)

            ###### HI-64 #####

            with m.Case(MicrOp.OP_MUL_H64):
                comb += Assume(~rec.is_32bit)

                exp_prod = Signal(128)

                # unsigned hi64 - mulhdu
                with m.If(~rec.is_signed):
                    comb += exp_prod.eq(a[0:64] * b[0:64])
                    comb += Assert(o[0:64] == exp_prod[64:128])

                # signed hi64 - mulhd
                with m.Else():
                    # Per rules of signed multiplication, if input signs
                    # differ, we negate the product.  This implies that
                    # the product is calculated from the absolute values
                    # of the inputs.
                    prod = Signal.like(exp_prod) # intermediate product
                    comb += prod.eq(abs64_a * abs64_b)
                    comb += exp_prod.eq(Mux(ab64_sne, -prod, prod))
                    comb += Assert(o[0:64] == exp_prod[64:128])

            ###### LO-64 #####
            # mulli, mullw(o)(u), mulld(o)

            with m.Case(MicrOp.OP_MUL_L64):

                with m.If(rec.is_32bit):                  # 32-bit mode
                    expected_ov = Signal()
                    prod = Signal(64)
                    exp_prod = Signal.like(prod)

                    # unsigned lo32 - mullwu
                    with m.If(~rec.is_signed):
                        comb += exp_prod.eq(a[0:32] * b[0:32])
                        comb += Assert(o[0:64] == exp_prod[0:64])

                    # signed lo32 - mullw
                    with m.Else():
                        # Per rules of signed multiplication, if input signs
                        # differ, we negate the product.  This implies that
                        # the product is calculated from the absolute values
                        # of the inputs.
                        comb += prod.eq(abs32_a[0:64] * abs32_b[0:64])
                        comb += exp_prod.eq(Mux(ab32_sne, -prod, prod))
                        comb += Assert(o[0:64] == exp_prod[0:64])

                    # see notes on overflow detection, above
                    m31 = exp_prod[31:64]
                    comb += expected_ov.eq(m31.bool() & ~m31.all())
                    comb += enable_overflow.eq(1)
                    comb += Assert(xer_ov_o == Repl(expected_ov, 2))

                with m.Else():                       # is 64-bit; mulld
                    expected_ov = Signal()
                    prod = Signal(128)
                    exp_prod = Signal.like(prod)

                    # From my reading of the v3.0B ISA spec,
                    # only signed instructions exist.
                    #
                    # Per rules of signed multiplication, if input signs
                    # differ, we negate the product.  This implies that
                    # the product is calculated from the absolute values
                    # of the inputs.
                    comb += Assume(rec.is_signed)
                    comb += prod.eq(abs64_a[0:64] * abs64_b[0:64])
                    comb += exp_prod.eq(Mux(ab64_sne, -prod, prod))
                    comb += Assert(o[0:64] == exp_prod[0:64])

                    # see notes on overflow detection, above
                    m63 = exp_prod[63:128]
                    comb += expected_ov.eq(m63.bool() & ~m63.all())
                    comb += enable_overflow.eq(1)
                    comb += Assert(xer_ov_o == Repl(expected_ov, 2))

            # not any of the cases above, disable result checking
            with m.Default():
                comb += result_ok.eq(0)

        # check result "write" is correctly requested
        comb += Assert(dut.o.o.ok == result_ok)
        comb += Assert(xer_ov_ok == enable_overflow)

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
