from nmigen import Signal, Module
from nmigen.back.pysim import Simulator, Delay, Settle
from nmutil.formaltest import FHDLTestCase
from nmigen.cli import rtlil
from soc.fu.compunits.compunits import FunctionUnitBaseSingle
from soc.experiment.alu_hier import DummyALU
from soc.experiment.compalu_multi import MultiCompUnit
from soc.fu.alu.alu_input_record import CompALUOpSubset
from openpower.decoder.power_enums import MicrOp
import unittest

class MaskGenTestCase(FHDLTestCase):
    def test_maskgen(self):
        m = Module()
        comb = m.d.comb
        alu = DummyALU(16)
        m.submodules.dut = dut = MultiCompUnit(16, alu,
                                               CompALUOpSubset)
        sim = Simulator(m)

        def process():
            yield dut.src1_i.eq(0x5)
            yield dut.src2_i.eq(0x5)
            yield dut.issue_i.eq(1)
            yield dut.oper_i.insn_type.eq(MicrOp.OP_ADD)
            yield
            yield dut.issue_i.eq(0)
            yield
            while True:
                yield
                rd_rel = yield dut.rd.rel
                if rd_rel != 0:
                    break
            yield dut.rd.go.eq(0xfff)
            yield
            yield dut.rd.go.eq(0)
            for i in range(10):
                yield
                


        sim.add_clock(1e-6)
        sim.add_sync_process(process)
        with sim.write_vcd("compunit.vcd", "compunit.gtkw", traces=dut.ports()):
            sim.run()

if __name__ == '__main__':
    unittest.main()
