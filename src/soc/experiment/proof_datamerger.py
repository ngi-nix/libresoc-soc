# Proof of correctness for partitioned equal signal combiner
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>
# Copyright (C) 2020 Tobias Platen <tplaten@posteo.de>

from nmigen import (Module, Signal, Elaboratable, Mux, Cat, Repl,
                    signed)
from nmigen.asserts import Assert, AnyConst, AnySeq, Assume, Cover
from nmigen.test.utils import FHDLTestCase
from nmigen.cli import rtlil

from soc.experiment.l0_cache import DataMerger

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

        array_size = 8
        m.submodules.dut = dut = DataMerger(array_size)

        # assign anyseq to inputs
        for j in range(dut.array_size):
            comb += dut.addr_array_i[j].eq(AnySeq(dut.array_size))
            comb += dut.data_i[j].eq(AnySeq(16+128))

        allzero = 1
        for j in range(dut.array_size):
            allzero = (dut.addr_array_i[j] == 0) & allzero

        # assert that the output is zero when the datamerger is idle
        with m.If(allzero):
            comb += Assert(dut.data_o == 0)
        with m.Else():
            TODO

        return m


class DataMergerTestCase(FHDLTestCase):
    def test_formal(self):
        module = Driver()
        # bounded model check first
        self.assertFormal(module, mode="bmc", depth=2)
        # self.assertFormal(module, mode="cover", depth=2)     # case can happen
        # XXX self.assertFormal(module, mode="prove")          # uses induction

    def test_ilang(self):
        dut = Driver()
        vl = rtlil.convert(dut, ports=[])
        with open("main_stage.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
