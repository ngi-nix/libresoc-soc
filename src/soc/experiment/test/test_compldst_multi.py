"""Self-contained unit test for the Load/Store CompUnit
"""

import unittest
from nmigen import Module
from nmigen.sim import Simulator
from soc.experiment.compldst_multi import LDSTCompUnit
from soc.experiment.pimem import PortInterface
from soc.fu.ldst.pipe_data import LDSTPipeSpec


class TestLDSTCompUnit(unittest.TestCase):

    def test_ldst_compunit(self):
        m = Module()
        pi = PortInterface(name="pi")
        regspec = LDSTPipeSpec.regspec
        dut = LDSTCompUnit(pi, regspec)
        m.submodules.dut = dut
        sim = Simulator(m)
        sim.add_clock(1e-6)

        def process():
            yield

        sim.add_sync_process(process)
        sim_writer = sim.write_vcd("test_ldst_compunit.vcd")
        with sim_writer:
            sim.run()


if __name__ == '__main__':
    unittest.main()
