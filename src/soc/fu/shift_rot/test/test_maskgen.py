from nmigen import Signal, Module
from nmigen.back.pysim import Simulator, Delay, Settle
from nmutil.formaltest import FHDLTestCase
from nmigen.cli import rtlil
from soc.fu.shift_rot.maskgen import MaskGen
from openpower.decoder.helpers import MASK
import random
import unittest

class MaskGenTestCase(FHDLTestCase):
    def test_maskgen(self):
        m = Module()
        comb = m.d.comb
        m.submodules.dut = dut = MaskGen(64)
        mb = Signal.like(dut.mb)
        me = Signal.like(dut.me)
        o = Signal.like(dut.o)

        comb += [
            dut.mb.eq(mb),
            dut.me.eq(me),
            o.eq(dut.o)]

        sim = Simulator(m)

        def process():
            for x in range(0, 64):
                for y in range(0, 64):
                    yield mb.eq(x)
                    yield me.eq(y)
                    yield Delay(1e-6)

                    expected = MASK(x, y)
                    result = yield o
                    self.assertEqual(expected, result)

        sim.add_process(process) # or sim.add_sync_process(process), see below
        with sim.write_vcd("maskgen.vcd", "maskgen.gtkw", traces=dut.ports()):
            sim.run()

    def test_ilang(self):
        dut = MaskGen(64)
        vl = rtlil.convert(dut, ports=dut.ports())
        with open("maskgen.il", "w") as f:
            f.write(vl)

if __name__ == '__main__':
    unittest.main()
