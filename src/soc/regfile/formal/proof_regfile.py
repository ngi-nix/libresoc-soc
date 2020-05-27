# This is the proof for Regfile class from regfile/regfile.py

from nmigen import (Module, Signal, Elaboratable, Mux, Cat, Repl,
                    signed, ResetSignal)
from nmigen.asserts import (Assert, AnyConst, Assume, Cover, Initial,
                            Rose, Fell, Stable, Past)
from nmigen.test.utils import FHDLTestCase
from nmigen.cli import rtlil
import unittest

from soc.regfile.regfile import Register


class Driver(Elaboratable):
    def __init__(self):
        pass

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        m.submodules.dut = dut = Register(32)

        width     = dut.width
        writethru = dut.writethru
        _rdports  = dut._rdports
        _wrports  = dut._wrports
        reg       = dut.reg

        for i in range(8):
            dut.read_port(f"{i}")
            dut.write_port(f"{i}")

        comb += reg.eq(AnyConst(32))

        for i in range(0,len(_rdports)):
            with m.If(_rdports[i].ren & writethru):
                with m.If(_wrports[i].wen):
                    comb += Assert(rdports[i].data_o == _wrports[i].data_i)
                with m.Else():
                    comb += Assert(rdports[i].data_o == reg)
            with m.Else():
                comb += Assert(_rdports[i].data_o == reg)

        return m


class TestCase(FHDLTestCase):
    def test_formal(self):
        module = Driver()
        self.assertFormal(module, mode="bmc", depth=2)
        self.assertFormal(module, mode="cover", depth=2)

    def test_ilang(self):
        dut = Driver()
        vl = rtlil.convert(dut, ports=[])
        with open("regfile.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
