from nmigen import (Cat, Const, Elaboratable, Module, Signal, signed)
from nmigen.asserts import (Assert, AnyConst, AnySeq, Assume)
from nmutil.formaltest import FHDLTestCase
from nmutil.stageapi import StageChain
from nmigen.cli import rtlil

import unittest

from soc.experiment.icache import ICache

from nmigen_soc.wishbone.sram import SRAM
from nmigen import Memory

class Driver(Elaboratable):
    def elaborate(self, platform):
        m     = Module()
        comb  = m.d.comb
        sync  = m.d.sync

        mem_init = [(i*2) | ((i*2+1) << 32) for i in range(512)]
        memory   = Memory(width=64, depth=512, init=mem_init)
        sram     = SRAM(memory=memory, granularity=8)

        m.submodules.dut  = dut = ICache()
        m.submodules.sram = sram

        m.d.comb += sram.bus.cyc.eq(dut.wb_out.cyc)
        m.d.comb += sram.bus.stb.eq(dut.wb_out.stb)
        m.d.comb += sram.bus.we.eq(dut.wb_out.we)
        m.d.comb += sram.bus.sel.eq(dut.wb_out.sel)
        m.d.comb += sram.bus.adr.eq(dut.wb_out.adr)
        m.d.comb += sram.bus.dat_w.eq(dut.wb_out.dat)

        m.d.comb += dut.wb_in.ack.eq(sram.bus.ack)
        m.d.comb += dut.wb_in.dat.eq(sram.bus.dat_r)

        i_out     = dut.i_in
        i_in      = dut.i_out
        m_out     = dut.m_in
        stall_in  = dut.stall_in
        stall_out = dut.stall_out
        flush_in  = dut.flush_in
        inval_in  = dut.inval_in
        wb_in     = dut.wb_in
        wb_out    = dut.wb_out
        log_out   = dut.log_out


class ICacheTestCase(FHDLTestCase):
    def test_formal(self):
        self.assertFormal(Driver(), mode="bmc", depth=10)
        self.assertFormal(Driver(), mode="cover", depth=10)

    def test_ilang(self):
        vl = rtlil.convert(Driver(), ports=[])
        with open("icache_formal.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
