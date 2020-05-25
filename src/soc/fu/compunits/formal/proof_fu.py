# This is the proof for the computation unit/Function Unit/ALU
# manager. Description here:
# https://libre-soc.org/3d_gpu/architecture/compunit/

# This attempts to prove most of the bullet points on that page


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

        issue = dut.issue_i
        busy = dut.busy_o

        go_rd = dut.rd.go
        rd_rel = dut.rd.rel

        go_wr = dut.wr.go
        wr_rel = dut.wr.rel

        go_die = dut.go_die_i
        shadow = dut.shadown_i

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

            # detect when issue has been raised and remember it
            with m.If(issue):
                sync += has_issued.eq(1)
                comb += Cover(has_issued)

            # Property 1: after an issue, busy should be raised
            with m.If(Past(issue)):
                comb += Assert(busy)

            # Property 2: After a wr_rel and go_wr, busy should be lowered
            with m.If(Past(wr_rel) & Past(go_wr)):
                # Shadow interferes with this and I'm not sure what is
                # correct
                with m.If(~Past(shadow)):
                    comb += Assert(busy == 0)
            with m.Elif(Past(busy) == 1):
                comb += Assert(busy == 1)

            # Property 3: Rd_rel should never be asserted before issue

            # If issue has never been raised, then rd_rel should never
            # be raised
            with m.If(rd_rel != 0):
                comb += Assert(has_issued)

            # Property 4: when rd_rel is asserted, it should stay
            # that way until a go_rd
            with m.If((Past(go_rd) == 0) & ~Past(go_die)):
                comb += Assert(~Fell(rd_rel))

            # Property 5: when a bit in rd_rel is asserted, and
            # the corresponding bit in go_rd is asserted, then that
            # bit of rd_rel should be deasserted
            for i in range(2):
                with m.If(Past(go_rd)[i] & (Past(rd_rel) != 0)):
                    comb += Assert(rd_rel[i] == ~Past(go_rd)[i])

            # Property 6: Similarly, if rd_rel is asserted,
            # asserting go_die should make rd_rel be deasserted

            with m.If(Past(rd_rel) != 0):
                with m.If(Past(go_die)):
                    comb += Assert(rd_rel == 0)

            comb += Cover(Fell(rd_rel))

            # Property 7: Similar to property 3, wr_rel should
            # never be asserted unless there was a preceeding issue

            with m.If(wr_rel != 0):
                comb += Assert(has_issued)

            # Property 8: Similar to property 4, wr_rel should stay
            # asserted until a go_rd, go_die, or shadow

            with m.If((Past(go_wr) == 0) & ~Past(go_die, 2) &
                      ~Past(shadow)):
                comb += Assert(~Fell(wr_rel))
            # Assume go_wr is not asserted unless wr_rel is
            with m.If(wr_rel == 0):
                comb += Assume(go_wr == 0)


            # Property 9: Similar to property 5, when wr_rel is
            # asserted and go_wr is asserted, then wr_rel should be
            # deasserted
            with m.If(Past(wr_rel) & Past(go_wr)):
                comb += Assert(wr_rel == 0)


            # Property 10: Similar to property 6, wr_rel should be
            # deasserted when go_die is asserted
            with m.If(Past(wr_rel) & Past(go_die)):
                comb += Assert(wr_rel == 0)

            # Property 11: wr_rel should not fall while shadow is
            # asserted
            with m.If(wr_rel & shadow):
                comb += Assert(~Fell(wr_rel))

            # Assume no instruction is issued until rd_rel is
            # released. Idk if this is valid

            with m.If(busy):
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
