# Proof of correctness for partitioned equal signal combiner
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>
"""
Links:
 * https://bugs.libre-soc.org/show_bug.cgi?id=331
 * https://libre-soc.org/openpower/isa/fixedlogical/
"""

from nmigen import (Module, Signal, Elaboratable, Mux, Cat, Repl,
                    signed)
from nmigen.asserts import Assert, AnyConst, Assume, Cover
from nmutil.formaltest import FHDLTestCase
from nmigen.lib.coding import PriorityEncoder
from nmigen.cli import rtlil

from soc.fu.logical.main_stage import LogicalMainStage
from soc.fu.alu.pipe_data import ALUPipeSpec
from soc.fu.alu.alu_input_record import CompALUOpSubset
from openpower.decoder.power_enums import MicrOp
import unittest


def simple_popcount(sig, width):
    """simple, naive (and obvious) popcount.
    formal verification does not to be fast: it does have to be correct
    """
    result = 0
    for i in range(width):
        result = result + sig[i]
    return result


# This defines a module to drive the device under test and assert
# properties about its outputs
class Driver(Elaboratable):
    def __init__(self):
        # inputs and outputs
        pass

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        rec = CompALUOpSubset()
        # Setup random inputs for dut.op
        for p in rec.ports():
            width = p.width
            comb += p.eq(AnyConst(width))

        pspec = ALUPipeSpec(id_wid=2)
        m.submodules.dut = dut = LogicalMainStage(pspec)

        # convenience variables
        a = dut.i.a
        b = dut.i.b
        #carry_in = dut.i.xer_ca[0]
        #carry_in32 = dut.i.xer_ca[1]
        o = dut.o.o.data

        # setup random inputs
        comb += [a.eq(AnyConst(64)),
                 b.eq(AnyConst(64)),
                 #carry_in.eq(AnyConst(0b11)),
                 ]

        comb += dut.i.ctx.op.eq(rec)

        # Assert that op gets copied from the input to output
        for rec_sig in rec.ports():
            name = rec_sig.name
            dut_sig = getattr(dut.o.ctx.op, name)
            comb += Assert(dut_sig == rec_sig)

        # signed and signed/32 versions of input a
        a_signed = Signal(signed(64))
        a_signed_32 = Signal(signed(32))
        comb += a_signed.eq(a)
        comb += a_signed_32.eq(a[0:32])

        o_ok = Signal()
        comb += o_ok.eq(1) # will be set to zero if no op takes place

        # main assertion of arithmetic operations
        with m.Switch(rec.insn_type):
            with m.Case(MicrOp.OP_AND):
                comb += Assert(o == a & b)
            with m.Case(MicrOp.OP_OR):
                comb += Assert(o == a | b)
            with m.Case(MicrOp.OP_XOR):
                comb += Assert(o == a ^ b)

            with m.Case(MicrOp.OP_POPCNT):
                with m.If(rec.data_len == 8):
                    comb += Assert(o == simple_popcount(a, 64))
                with m.If(rec.data_len == 4):
                    for i in range(2):
                        slc = slice(i*32, (i+1)*32)
                        comb += Assert(o[slc] == simple_popcount(a[slc], 32))
                with m.If(rec.data_len == 1):
                    for i in range(8):
                        slc = slice(i*8, (i+1)*8)
                        comb += Assert(o[slc] == simple_popcount(a[slc], 8))

            with m.Case(MicrOp.OP_PRTY):
                with m.If(rec.data_len == 8):
                    result = 0
                    for i in range(8):
                        result = result ^ a[i*8]
                    comb += Assert(o == result)
                with m.If(rec.data_len == 4):
                    result_low = 0
                    result_high = 0
                    for i in range(4):
                        result_low = result_low ^ a[i*8]
                        result_high = result_high ^ a[i*8 + 32]
                    comb += Assert(o[0:32] == result_low)
                    comb += Assert(o[32:64] == result_high)

            with m.Case(MicrOp.OP_CNTZ):
                XO = dut.fields.FormX.XO[0:-1]
                with m.If(rec.is_32bit):
                    m.submodules.pe32 = pe32 = PriorityEncoder(32)
                    peo = Signal(range(0, 32+1))
                    with m.If(pe32.n):
                        comb += peo.eq(32)
                    with m.Else():
                        comb += peo.eq(pe32.o)
                    with m.If(XO[-1]): # cnttzw
                        comb += pe32.i.eq(a[0:32])
                        comb += Assert(o == peo)
                    with m.Else(): # cntlzw
                        comb += pe32.i.eq(a[0:32][::-1])
                        comb += Assert(o == peo)
                with m.Else():
                    m.submodules.pe64 = pe64 = PriorityEncoder(64)
                    peo64 = Signal(7)
                    with m.If(pe64.n):
                        comb += peo64.eq(64)
                    with m.Else():
                        comb += peo64.eq(pe64.o)
                    with m.If(XO[-1]): # cnttzd
                        comb += pe64.i.eq(a[0:64])
                        comb += Assert(o == peo64)
                    with m.Else(): # cntlzd
                        comb += pe64.i.eq(a[0:64][::-1])
                        comb += Assert(o == peo64)

            with m.Case(MicrOp.OP_CMPB):
                for i in range(8):
                    slc = slice(i*8, (i+1)*8)
                    with m.If(a[slc] == b[slc]):
                        comb += Assert(o[slc] == 0xff)
                    with m.Else():
                        comb += Assert(o[slc] == 0)

            with m.Case(MicrOp.OP_BPERM):
                # note that this is a copy of the beautifully-documented
                # proof_bpermd.py
                comb += Assert(o[8:] == 0)
                for i in range(8):
                    index = a[i*8:i*8+8]
                    with m.If(index >= 64):
                        comb += Assert(o[i] == 0)
                    with m.Else():
                        for j in range(64):
                            with m.If(index == j):
                                comb += Assert(o[i] == b[63-j])

            with m.Default():
                comb += o_ok.eq(0)

        # check that data ok was only enabled when op actioned
        comb += Assert(dut.o.o.ok == o_ok)

        return m


class LogicalTestCase(FHDLTestCase):
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
