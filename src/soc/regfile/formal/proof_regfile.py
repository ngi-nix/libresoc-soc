# This is the proof for Regfile class from regfile/regfile.py

from nmigen import (Module, Signal, Elaboratable, Mux, Cat, Repl,
                    signed, ResetSignal)
from nmigen.asserts import (Assert, AnyConst, Assume, Cover, Initial,
                            Rose, Fell, Stable, Past)
from nmigen.test.utils import FHDLTestCase
from nmigen.cli import rtlil
import unittest

from soc.regfile.regfile import Register


class Driver(Register):
    def __init__(self):
        super().__init__(8)

    def elaborate(self, platform):
        m = super().elaborate(platform)
        comb = m.d.comb

        width     = self.width
        writethru = self.writethru
        _rdports  = self._rdports
        _wrports  = self._wrports
        reg       = self.reg

        for i in range(8):
            self.read_port(f"{i}")
            self.write_port(f"{i}")

        comb += reg.eq(AnyConst(8))

        for i in range(len(_rdports)):
            with m.If(_rdports[i].ren & writethru):
                with m.If(_wrports[i].wen):
                    comb += Assert(_rdports[i].data_o == _wrports[i].data_i)
                with m.Else():
                    comb += Assert(_rdports[i].data_o == reg)
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
