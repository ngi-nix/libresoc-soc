# https://github.com/antonblanchard/microwatt/blob/master/countzero_tb.vhdl
from nmigen import Module, Signal
from nmigen.cli import rtlil
from nmigen.back.pysim import Simulator, Delay
from nmutil.formaltest import FHDLTestCase
import unittest
from soc.fu.logical.countzero import ZeroCounter


class ZeroCounterTestCase(FHDLTestCase):
    def test_zerocounter(self):
        m = Module()
        comb = m.d.comb
        m.submodules.dut = dut = ZeroCounter()

        sim = Simulator(m)
        # sim.add_clock(1e-6)

        def process():
            print("test zero input")
            yield dut.rs_i.eq(0)
            yield dut.is_32bit_i.eq(0)
            yield dut.count_right_i.eq(0)
            yield Delay(1e-6)
            result = yield dut.result_o
            assert result == 0x40
            # report "bad cntlzd 0 = " & to_hstring(result);
            assert(result == 0x40)
            yield dut.count_right_i.eq(1)
            yield Delay(1e-6)
            result = yield dut.result_o
            # report "bad cntlzd 0 = " & to_hstring(result);
            assert(result == 0x40)
            yield dut.is_32bit_i.eq(1)
            yield dut.count_right_i.eq(0)
            yield Delay(1e-6)
            result = yield dut.result_o
            # report "bad cntlzw 0 = " & to_hstring(result);
            assert(result == 0x20)
            yield dut.count_right_i.eq(1)
            yield Delay(1e-6)
            result = yield dut.result_o
            # report "bad cntlzw 0 = " & to_hstring(result);
            assert(result == 0x20)
            # TODO next tests

            yield dut.rs_i.eq(0b00010000)
            yield dut.is_32bit_i.eq(0)
            yield dut.count_right_i.eq(0)
            yield Delay(1e-6)
            result = yield dut.result_o
            assert result == 4, "result %d" % result

            yield dut.count_right_i.eq(1)
            yield Delay(1e-6)
            result = yield dut.result_o
            assert result == 59, "result %d" % result

            yield dut.is_32bit_i.eq(1)
            yield Delay(1e-6)
            result = yield dut.result_o
            assert result == 27, "result %d" % result

            yield dut.rs_i.eq(0b1100000100000000)
            yield dut.is_32bit_i.eq(0)
            yield dut.count_right_i.eq(0)
            yield Delay(1e-6)
            result = yield dut.result_o
            assert result == 14, "result %d" % result

            yield dut.count_right_i.eq(1)
            yield Delay(1e-6)
            result = yield dut.result_o
            assert result == 55, "result %d" % result

            yield dut.is_32bit_i.eq(1)
            yield Delay(1e-6)
            result = yield dut.result_o
            assert result == 23, "result %d" % result

            yield dut.count_right_i.eq(0)
            yield Delay(1e-6)
            result = yield dut.result_o
            assert result == 14, "result %d" % result


        sim.add_process(process)  # or sim.add_sync_process(process), see below

        # run test and write vcd
        fn = "countzero"
        with sim.write_vcd(fn+".vcd", fn+".gtkw", traces=dut.ports()):
            sim.run()

    # cntlzd_w
    # cnttzd_w


if __name__ == "__main__":

    dut = ZeroCounter()
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("countzero.il", "w") as f:
        f.write(vl)

    unittest.main()
