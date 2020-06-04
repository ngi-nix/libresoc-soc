# This is the proof for the computation unit/Function Unit/ALU
# manager. Description here:
# https://libre-soc.org/3d_gpu/architecture/compunit/

# This attempts to prove most of the bullet points on that page

from nmigen import (Module, Signal, Elaboratable, Mux, Cat, Repl,
                    signed, ResetSignal)
from nmigen.asserts import (Assert, AnyConst, Assume, Cover, Initial,
                            Rose, Fell, Stable, Past)
from nmutil.formaltest import FHDLTestCase
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
        m.submodules.dut = dut = MultiCompUnit(16, alu, CompALUOpSubset)

        issue = dut.issue_i
        busy = dut.busy_o

        go_rd = dut.rd.go
        rd_rel = dut.rd.rel

        go_wr = dut.wr.go
        wr_rel = dut.wr.rel

        go_die = dut.go_die_i
        shadow_n = dut.shadown_i

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

            # Property 1: When issue is first raised, a busy signal is
            # sent out. The operand can be latched in at this point
            # (rd_rel and go_rd are allowed to be high)

            # Busy should rise after issue.
            with m.If(Past(issue)):
                comb += Assert(Rose(busy))

            # Instructions should not be issued if busy == 1
            with m.If(busy):
                comb += Assume(issue == 0)

            # Property 2: Issue will only be raised for one
            # cycle. Read requests may go out immediately after issue
            # goes low


            # The read_request should not happen while the unit is not busy
            with m.If(~busy):
                comb += Assert(rd_rel == 0)

            # Property 3: Read request is sent, which is acknowledged
            # through the scoreboard to the priority picker which
            # generates one go_read at a time. One of those will
            # eventually be this computation unit

            # there cannot be a go_rd if rd_rel is clear
            with m.If(rd_rel == 0):
                comb += Assume(go_rd == 0)

            # Property 4: Once Go_Read is set, the src1/src2/operand
            # latch door shuts and the ALU is told to proceed

            # When a go_rd is received for each operand, the data
            # should be captured
            with m.If(~Past(go_die)):
                with m.If(Past(go_rd)[0] & Past(rd_rel)[0]):
                    comb += Assert(dut.alu.a == Past(dut.src1_i))
                with m.If(Past(go_rd)[1] & Past(rd_rel)[1]):
                    comb += Assert(dut.alu.b == Past(dut.src2_i))

            # Property 5: When the ALU pipeline is ready, this
            # activates write_request release and the ALU's output is
            # captured in a temporary register

            # I can't see the actual temporary register, so I have to
            # simulate it here. This will be checked when the ALU data
            # is actually output
            alu_temp = Signal(16)
            write_req_valid = Signal(reset=0)
            with m.If(~Past(go_die) & Past(busy)):
                with m.If(Rose(dut.alu.n.valid_o)):
                    sync += alu_temp.eq(dut.alu.o)
                    sync += write_req_valid.eq(1)

            # write_req_valid should only be high once the alu finishes
            with m.If(~write_req_valid & ~dut.alu.n.valid_o):
                comb += Assert(wr_rel == 0)

            # Property 6: Write request release is held up if shadow_n
            # is asserted low

            # If shadow_n is low (indicating that everything is
            # shadowed), wr_rel should not be able to rise
            with m.If(shadow_n == 0):
                with m.If(Past(wr_rel) == 0):
                    comb += Assert(wr_rel == 0)

            # Property 7: Write request release will go through a
            # similar process as read request, resulting (eventually
            # in go_write being asserted

            # Go_wr should not be asserted if wr_rel is not
            with m.If(wr_rel == 0):
                comb += Assume(go_wr == 0)


            # Property 8: When go_write is asserted, two things
            # happen. 1 - the data in the temp register is placed
            # combinatorially onto the output. And 2 - the req_l latch
            # is cleared, busy is dropped, and the comp unit is ready
            # to do another task

            # If a write release is accepted (by asserting go_wr),
            # then the alu data should be output
            with m.If(Past(wr_rel) & Past(go_wr)):
                # the alu data is output
                comb += Assert((dut.data_o == alu_temp) | (dut.data_o == dut.alu.o))
                # wr_rel is dropped
                comb += Assert(wr_rel == 0)
                # busy is dropped.
                with m.If(~Past(go_die)):
                    comb += Assert(busy == 0)


        # It is REQUIRED that issue be held valid only for one cycle
        with m.If(Past(issue)):
            comb += Assume(issue == 0)

        # It is REQUIRED that GO_Read be held valid only for one
        # cycle, and it is REQUIRED that the corresponding read_req be
        # dropped exactly one cycle after go_read is asserted high

        for i in range(2):
            with m.If(Past(go_rd)[i] & Past(rd_rel)[i]):
                comb += Assume(go_rd[i] == 0)
                comb += Assert(rd_rel[i] == 0)

        # Likewise for go_write/wr_rel
        with m.If(Past(go_wr) & Past(wr_rel)):
            comb += Assume(go_wr == 0)
            comb += Assert(wr_rel == 0)

        # When go_die is asserted the the entire FSM should be fully
        # reset.

        with m.If(Past(go_die) & Past(busy)):
            comb += Assert(rd_rel == 0)
            # this doesn't work?
            # comb += Assert(wr_rel == 0)
            sync += write_req_valid.eq(0)

        return m


class FUTestCase(FHDLTestCase):
    def test_formal(self):
        module = Driver()
        self.assertFormal(module, mode="bmc", depth=10)
        self.assertFormal(module, mode="cover", depth=10)
    def test_ilang(self):
        dut = MultiCompUnit(16, DummyALU(16), CompALUOpSubset)
        vl = rtlil.convert(dut, ports=dut.ports())
        with open("multicompunit.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
