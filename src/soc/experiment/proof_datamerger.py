# Proof of correctness for partitioned equal signal combiner
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>
# Copyright (C) 2020 Tobias Platen <tplaten@posteo.de>

from nmigen import (Module, Signal, Elaboratable, Mux, Cat, Repl,
                    signed)
from nmigen.asserts import Assert, AnyConst, Assume, Cover
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

        # convenience variables
        # Assert that op gets copied from the input to output
        
        # TODO: investigate error 
        "Object (rec <unnamed> data en) cannot be used as a key in value collections"
        return m


class DataMergerTestCase(FHDLTestCase):
    def test_formal(self):
        module = Driver()
        # self.assertFormal(module, mode="bmc", depth=2)
        # self.assertFormal(module, mode="cover", depth=2)
        self.assertFormal(module, mode="prove")
    def test_ilang(self):
        dut = Driver()
        vl = rtlil.convert(dut, ports=[])
        with open("main_stage.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
