from nmigen import (Module, Signal, Elaboratable, Mux, Cat, Repl,
                    signed, ResetSignal)
from nmigen.asserts import (Assert, AnyConst, Assume, Cover, Initial,
                            Rose, Fell, Stable, Past)
from nmigen.test.utils import FHDLTestCase
from nmigen.cli import rtlil
import unittest

from soc.fu.compunits.compunits import FunctionUnitBaseSingle
from soc.experiment.alu_hier import DummyALU
from soc.experiment.compalu_multi import MultiCompUnit
from soc.fu.alu.alu_input_record import CompALUOpSubset

class Driver(Elaboratable):
    def __init__(self):
        pass

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        sync = m.d.sync
        alu = DummyALU(16)
        m.submodules.dut = dut = MultiCompUnit(16, alu,
                                               CompALUOpSubset)

        go_rd = dut.rd.go
        rd_rel = dut.rd.rel
        issue = dut.issue_i

        go_die = dut.go_die_i

        rst = ResetSignal()

        init = Initial()

        has_issued = Signal(reset=0)



        with m.If(init):
            comb += Assume(has_issued == 0)
            comb += Assume(issue == 0)
            comb += Assume(go_rd == 0)
            comb += Assume(rst == 1)
        with m.Else():
            comb += Assume(rst == 0)

            # Property One: Rd_rel should never be asserted before issue

            # detect when issue has been raised and remember it
            with m.If(issue):
                sync += has_issued.eq(1)
                comb += Cover(has_issued)
            # If issue has never been raised, then rd_rel should never be raised
            with m.If(rd_rel != 0):
                comb += Assert(has_issued)


            # Property Two: when rd_rel is asserted, it should stay
            # that way until a go_rd
            with m.If((Past(go_rd) == 0) & ~Past(go_die)):
                comb += Assert(~Fell(rd_rel))

            # Property Three: when a bit in rd_rel is asserted, and
            # the corresponding bit in go_rd is asserted, then that
            # bit of rd_rel should be deasserted
            for i in range(2):
                with m.If(Past(go_rd)[i] & (Past(rd_rel) != 0)):
                    comb += Assert(rd_rel[i] == ~Past(go_rd)[i])

            # Property Four: Similarly, if rd_rel is asserted,
            # asserting go_die should make rd_rel be deasserted

            with m.If(Past(rd_rel) != 0):
                with m.If(Past(go_die)):
                    comb += Assert(rd_rel == 0)

            # Property 

            comb += Cover(Fell(rd_rel))

            # Assume no instruction is issued until rd_rel is
            # released. Idk if this is valid

            with m.If((rd_rel != 0) | (Past(rd_rel) != 0)):
                comb += Assume(issue == 0)
        




        return m

class FUTestCase(FHDLTestCase):
    def test_formal(self):
        module = Driver()
        self.assertFormal(module, mode="bmc", depth=5)
        self.assertFormal(module, mode="cover", depth=5)
    def test_ilang(self):
        dut = MultiCompUnit(16, DummyALU(16), CompALUOpSubset)
        vl = rtlil.convert(dut, ports=dut.ports())
        with open("multicompunit.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
