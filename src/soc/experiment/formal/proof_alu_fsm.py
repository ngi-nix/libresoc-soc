import unittest
import os

from nmigen import Elaboratable, Signal, Module
from nmigen.asserts import Assert, Assume, Cover, Past, Stable
from nmigen.cli import rtlil

from nmutil.formaltest import FHDLTestCase
from nmutil.gtkw import write_gtkw

from soc.experiment.alu_fsm import Shifter


# This defines a module to drive the device under test and assert
# properties about its outputs
class Driver(Elaboratable):
    def __init__(self):
        # inputs and outputs
        pass

    @staticmethod
    def elaborate(_):
        m = Module()
        comb = m.d.comb
        sync = m.d.sync

        m.submodules.dut = dut = Shifter(8)
        # Coverage condition (one bit for each coverage case)
        cov = Signal(8)
        # input data to the shifter
        data_i = Signal(8)
        shift_i = Signal(8)
        op_sdir = Signal()
        # expected result
        expected = Signal(8)
        # transaction count for each port
        write_cnt = Signal(4)
        read_cnt = Signal(4)
        # liveness counter
        live_cnt = Signal(5)
        # keep data and valid stable, until accepted
        with m.If(Past(dut.p.valid_i) & ~Past(dut.p.ready_o)):
            comb += [
                Assume(Stable(dut.op.sdir)),
                Assume(Stable(dut.p.data_i.data)),
                Assume(Stable(dut.p.data_i.shift)),
                Assume(Stable(dut.p.valid_i)),
            ]
        # force reading the output in a reasonable time,
        # necessary to pass induction
        with m.If(Past(dut.n.valid_o) & ~Past(dut.n.ready_i)):
            comb += Assume(dut.n.ready_i)
        # capture transferred input data
        with m.If(dut.p.ready_o & dut.p.valid_i):
            sync += [
                data_i.eq(dut.p.data_i.data),
                shift_i.eq(dut.p.data_i.shift),
                op_sdir.eq(dut.op.sdir),
                # increment write counter
                write_cnt.eq(write_cnt + 1),
            ]
            # calculate the expected result
            dut_data_i = dut.p.data_i.data
            dut_shift_i = dut.p.data_i.shift[:4]
            dut_sdir = dut.op.sdir
            with m.If(dut_sdir):
                sync += expected.eq(dut_data_i >> dut_shift_i)
            with m.Else():
                sync += expected.eq(dut_data_i << dut_shift_i)
        # Check for dropped inputs, by ensuring that there are no more than
        # one work item ever in flight at any given time.
        # Whenever the unit is busy (not ready) the read and write counters
        # will differ by exactly one unit.
        m.d.comb += Assert((read_cnt + ~dut.p.ready_o) & 0xF == write_cnt)
        # Check for liveness. It will ensure that the FSM is not stuck, and
        # will eventually produce some result.
        # In this case, the delay between ready_o being negated and valid_o
        # being asserted has to be less than 16 cycles.
        with m.If(~dut.p.ready_o & ~dut.n.valid_o):
            m.d.sync += live_cnt.eq(live_cnt + 1)
        with m.Else():
            m.d.sync += live_cnt.eq(0)
        m.d.comb += Assert(live_cnt < 16)
        # check coverage as output data is accepted
        with m.If(dut.n.ready_i & dut.n.valid_o):
            # increment read counter
            sync += read_cnt.eq(read_cnt + 1)
            # check result
            comb += Assert(dut.n.data_o.data == expected)
            # cover zero data, with zero and non-zero shift
            # (any direction)
            with m.If(data_i == 0):
                with m.If(shift_i == 0):
                    sync += cov[0].eq(1)
                with m.If(shift_i[:3].any() & ~shift_i[3]):
                    sync += cov[1].eq(1)
            # cover non-zero data, with zero and non-zero shift
            # (both directions)
            with m.If(data_i != 0):
                with m.If(shift_i == 0):
                    sync += cov[2].eq(1)
                with m.If(shift_i[:3].any() & ~shift_i[3]):
                    with m.If(op_sdir):
                        sync += cov[3].eq(1)
                    with m.Else():
                        sync += cov[4].eq(1)
                # cover big shift
                with m.If(shift_i[3] != 0):
                    sync += cov[5].eq(1)
            # cover non-zero shift giving non-zero result
            with m.If(data_i.any() & shift_i.any() & dut.n.data_o.data.any()):
                sync += cov[6].eq(1)
            # dummy condition, to avoid optimizing-out the counters
            with m.If((write_cnt != 0) | (read_cnt != 0)):
                sync += cov[7].eq(1)
        # check that each condition above occurred at least once
        comb += Cover(cov.all())
        return m


class ALUFSMTestCase(FHDLTestCase):
    def test_formal(self):
        traces = [
            'clk',
            'p_data_i[7:0]', 'p_shift_i[7:0]', 'op__sdir',
            'p_valid_i', 'p_ready_o',
            'n_data_o[7:0]',
            'n_valid_o', 'n_ready_i',
            ('formal', {'module': 'top'}, [
                'write_cnt[3:0]', 'read_cnt[3:0]', 'cov[7:0]'
            ])
        ]
        write_gtkw(
            'test_formal_cover_alu_fsm.gtkw',
            os.path.dirname(__file__) +
            '/proof_alu_fsm_formal/engine_0/trace0.vcd',
            traces,
            module='top.dut',
            zoom=-6.3
        )
        write_gtkw(
            'test_formal_bmc_alu_fsm.gtkw',
            os.path.dirname(__file__) +
            '/proof_alu_fsm_formal/engine_0/trace.vcd',
            traces,
            module='top.dut',
            zoom=-6.3
        )
        write_gtkw(
            'test_formal_induct_alu_fsm.gtkw',
            os.path.dirname(__file__) +
            '/proof_alu_fsm_formal/engine_0/trace_induct.vcd',
            traces,
            module='top.dut',
            zoom=-6.3
        )
        module = Driver()
        self.assertFormal(module, mode="prove", depth=18)
        self.assertFormal(module, mode="cover", depth=32)

    @staticmethod
    def test_rtlil():
        dut = Driver()
        vl = rtlil.convert(dut, ports=[])
        with open("alu_fsm.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
