# This is the proof for Regfile class from regfile/regfile.py

from nmigen import (Module, Signal, Elaboratable, Mux, Cat, Repl,
                    signed, ResetSignal)
from nmigen.asserts import (Assert, AnySeq, Assume, Cover, Initial,
                            Rose, Fell, Stable, Past)
from nmutil.formaltest import FHDLTestCase
from nmigen.cli import rtlil
import unittest

from soc.regfile.regfile import Register


class Driver(Register):
    def __init__(self, writethru=True):
        super().__init__(8, writethru)
        for i in range(1): # just do one for now
            self.read_port(f"{i}")
            self.write_port(f"{i}")

    def elaborate(self, platform):
        m = super().elaborate(platform)
        comb = m.d.comb
        sync = m.d.sync

        width     = self.width
        writethru = self.writethru
        _rdports  = self._rdports
        _wrports  = self._wrports


        comb += _wrports[0].data_i.eq(AnySeq(8))
        comb += _wrports[0].wen.eq(AnySeq(1))
        comb += _rdports[0].ren.eq(AnySeq(1))

        rst = ResetSignal()

        init = Initial()

        # Most likely incorrect 4-way truth table
        #
        # rp.ren  wp.wen  rp.data_o            reg
        # 0       0       zero                 should be previous value
        # 0       1       zero                 wp.data_i
        # 1       0       reg                  should be previous value
        # 1       1       wp.data_i            wp.data_i

        # Holds the value written to the register when a write happens
        register_data = Signal(self.width)
        register_written = Signal()

        # Make sure we're actually hitting a read and write
        comb += Cover(_rdports[0].ren & register_written)

        with m.If(init):
            comb += Assume(rst == 1)
            for port in _rdports:
                comb += Assume(port.ren == 0)
            for port in _wrports:
                comb += Assume(port.wen == 0)

            comb += Assume(register_written == 0)

        with m.Else():
            comb += Assume(rst == 0)

            # If there is no read, then data_o should be 0
            with m.If(_rdports[0].ren == 0):
                comb += Assert(_rdports[0].data_o == 0)

            # If there is a read request
            with m.Else():
                if writethru:
                    # Since writethrough is enabled, we need to check
                    # if we're writing while reading. If so, then the
                    # data from the read port should be the same as
                    # that of the write port
                    with m.If(_wrports[0].wen):
                        comb += Assert(_rdports[0].data_o ==
                                       _wrports[0].data_i)

                    # Otherwise, check to make sure the register has
                    # been written to at some point, and make sure the
                    # data output matches the data that was written
                    # before
                    with m.Else():
                        with m.If(register_written):
                            comb += Assert(_rdports[0].data_o == register_data)

                else:
                    # Same as the Else branch above, make sure the
                    # read port data matches the previously written
                    # data
                    with m.If(register_written):
                        comb += Assert(_rdports[0].data_o == register_data)

            # If there is a write, store the data to be written to our
            # copy of the register and mark it as written
            with m.If(_wrports[0].wen):
                sync += register_data.eq(_wrports[0].data_i)
                sync += register_written.eq(1)

        return m


class TestCase(FHDLTestCase):
    def test_formal(self):
        for writethrough in [False, True]:
            module = Driver(writethrough)
            self.assertFormal(module, mode="bmc", depth=10)
            self.assertFormal(module, mode="cover", depth=10)

    def test_ilang(self):
        dut = Driver()
        vl = rtlil.convert(dut, ports=[])
        with open("regfile.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
