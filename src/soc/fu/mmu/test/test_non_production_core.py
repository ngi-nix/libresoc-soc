from nmigen import Module, Signal

from nmutil.sim_tmp_alternative import Simulator, Settle

from nmigen.cli import rtlil
import unittest
from openpower.decoder.isa.caller import ISACaller, special_sprs
from openpower.decoder.power_decoder import (create_pdecode)
from openpower.decoder.power_decoder2 import (PowerDecode2)
from openpower.decoder.power_enums import (XER_bits, Function, MicrOp, CryIn)
from openpower.decoder.selectable_int import SelectableInt
from openpower.simulator.program import Program
from openpower.decoder.isa.all import ISA
from openpower.endian import bigendian
from openpower.consts import MSR


from openpower.test.common import (
    TestAccumulatorBase, skip_case, TestCase, ALUHelpers)
import random

from soc.fu.div.test.helper import (log_rand, get_cu_inputs,
                                    set_alu_inputs, DivTestHelper)

from soc.simple.core import NonProductionCore
from soc.config.test.test_loadstore import TestMemPspec
from soc.simple.test.test_core import (setup_regs, check_regs,
                                       wait_for_busy_clear,
                                       wait_for_busy_hi)

debughang = 2

class MMUTestCase(TestAccumulatorBase):
    # MMU handles MTSPR, MFSPR, DCBZ and TLBIE.
    # other instructions here -> must be load/store

    def case_mfspr_after_invalid_load(self):
        lst = [ # TODO -- set SPR on both sinulator and port interface
                "mfspr 1, 18", # DSISR to reg 1
                "mfspr 2, 19", # DAR to reg 2
                # TODO -- verify returned sprvals
              ]

        initial_regs = [0] * 32

        #THOSE are currently broken -- initial_sprs = {'DSISR': 0x12345678, 'DAR': 0x87654321}
        initial_sprs = {}
        self.add_case(Program(lst, bigendian),
                      initial_regs, initial_sprs)

    #def case_ilang(self):
    #    pspec = SPRPipeSpec(id_wid=2)
    #    alu = SPRBasePipe(pspec)
    #    vl = rtlil.convert(alu, ports=alu.ports())
    #    with open("trap_pipeline.il", "w") as f:
    #        f.write(vl)


class TestRunner(unittest.TestCase):
    def __init__(self, test_data):
        super().__init__("run_all")
        self.test_data = test_data

    def execute(self, core, instruction, pdecode2, test):
        program = test.program
        sim = ISA(pdecode2, test.regs, test.sprs, test.cr,
                  test.mem, test.msr,
                  bigendian=bigendian)
        gen = program.generate_instructions()
        instructions = list(zip(gen, program.assembly.splitlines()))

        pc = sim.pc.CIA.value
        msr = sim.msr.value
        index = pc//4
        while index < len(instructions):
            ins, code = instructions[index]

            print("pc %08x instr: %08x" % (pc, ins & 0xffffffff))
            print(code)

            if 'XER' in sim.spr:
                so = 1 if sim.spr['XER'][XER_bits['SO']] else 0
                ov = 1 if sim.spr['XER'][XER_bits['OV']] else 0
                ov32 = 1 if sim.spr['XER'][XER_bits['OV32']] else 0
                print("before: so/ov/32", so, ov, ov32)

            # ask the decoder to decode this binary data (endian'd)
            yield pdecode2.dec.bigendian.eq(bigendian)  # little / big?
            yield pdecode2.state.msr.eq(msr)  # set MSR in pdecode2
            yield pdecode2.state.pc.eq(pc)  # set PC in pdecode2
            yield instruction.eq(ins)          # raw binary instr.
            yield Settle()

            yield from setup_regs(pdecode2, core, test)

            opname = code.split(' ')[0]
            yield from sim.call(opname)
            pc = sim.pc.CIA.value
            msr = sim.msr.value
            index = pc//4
            print("pc after %08x" % (pc))

            fsm = core.fus.fus["mmu0"].alu

            vld = yield fsm.n.valid_o
            while not vld:
                yield
                if debughang:  print("not valid -- hang")
                vld = yield fsm.n.valid_o
                if debughang==2: vld=1
            yield

    def run_all(self):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)

        pspec = TestMemPspec(ldst_ifacetype='testpi',
                             imem_ifacetype='',
                             addr_wid=48,
                             mask_wid=8,
                             reg_wid=64)

        m.submodules.core = core = NonProductionCore(pspec
                                     # XXX NO absolutely do not do this.
                                     # all options must go into the pspec
                                     #, microwatt_mmu=True
                                                        )

        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)

        sim.add_clock(1e-6)

        def process():
            for test in self.test_data:
                print("test", test.name)
                print("sprs", test.sprs)
                program = test.program
                with self.subTest(test.name):
                    yield from self.execute(core, instruction, pdecode2, test)

        sim.add_sync_process(process)
        with sim.write_vcd("mmu_ldst_simulator.vcd", "mmu_ldst_simulator.gtkw",
                           traces=[]):
            sim.run()

if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TestRunner(MMUTestCase().test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
