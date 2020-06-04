# This is the proof for Regfile class from regfile/regfile.py

from nmigen import (Module, Signal, Elaboratable, Mux, Cat, Repl,
                    signed, ResetSignal, Array)
from nmigen.asserts import (Assert, AnySeq, Assume, Cover, Initial,
                            Rose, Fell, Stable, Past)
from nmutil.formaltest import FHDLTestCase
from nmigen.cli import rtlil
import unittest
import math

from soc.regfile.regfile import RegFile


class Driver(RegFile):
    def __init__(self):
        super().__init__(width=8, depth=4)
        for i in range(1): # just do one for now
            self.read_port()
            self.write_port()

    def elaborate(self, platform):
        m = super().elaborate(platform)
        comb = m.d.comb
        sync = m.d.sync

        width     = self.width
        depth     = self.depth
        lg2depth  = int(math.ceil(math.log2(depth)))
        _rdports  = self._rdports
        _wrports  = self._wrports

        comb += _wrports[0].data_i.eq(AnySeq(8))
        
        comb += _wrports[0].wen.eq(AnySeq(1))
        comb += _wrports[0].waddr.eq(AnySeq(lg2depth))
        comb += _rdports[0].ren.eq(AnySeq(1))
        comb += _rdports[0].raddr.eq(AnySeq(lg2depth))

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
        register_data = Array([Signal(self.width, name=f"reg_data{i}")
                               for i in range(depth)])
        register_written = Array([Signal(name=f"reg_written{i}")
                                  for i in range(depth)])

        with m.If(init):
            comb += Assume(rst == 1)

            for i in range(depth):
                comb += Assume(register_written[i] == 0)

        with m.Else():
            comb += Assume(rst == 0)

            with m.If(_rdports[0].ren == 0):
                comb += Assert(_rdports[0].data_o == 0)

            # Read enable is active
            with m.Else():
                addr = _rdports[0].raddr
                # Check to see if there's a write on this
                # cycle. If so, then the output data should be
                # that of the write port
                with m.If(_wrports[0].wen & (_wrports[0].waddr == addr)):
                    comb += Assert(_rdports[0].data_o ==
                                   _wrports[0].data_i)
                    comb += Cover(1)

                # Otherwise the data output should be the
                # saved register
                with m.Elif(register_written[addr]):
                    comb += Assert(_rdports[0].data_o ==
                                   register_data[addr])
                    comb += Cover(1)

            # If there's a write to a given register, store that
            # data in a copy of the register, and mark it as
            # written
            with m.If(_wrports[0].wen):
                addr = _wrports[0].waddr
                sync += register_data[addr].eq(_wrports[0].data_i)
                sync += register_written[addr].eq(1)
                


        return m


class TestCase(FHDLTestCase):
    def test_formal(self):
        module = Driver()
        self.assertFormal(module, mode="bmc", depth=10)
        self.assertFormal(module, mode="cover", depth=10)

    def test_ilang(self):
        dut = Driver()
        vl = rtlil.convert(dut, ports=[])
        with open("regfile_binary.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
