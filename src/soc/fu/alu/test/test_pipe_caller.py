import random
from soc.fu.alu.pipe_data import ALUPipeSpec
from soc.fu.alu.pipeline import ALUBasePipe
from soc.fu.test.common import (TestCase, TestAccumulatorBase, ALUHelpers)
from soc.config.endian import bigendian
from soc.decoder.isa.all import ISA
from soc.simulator.program import Program
from soc.decoder.selectable_int import SelectableInt
from soc.decoder.power_enums import (XER_bits, Function, MicrOp, CryIn)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.isa.caller import ISACaller, special_sprs
import unittest
from nmigen.cli import rtlil
from nmutil.formaltest import FHDLTestCase
from nmigen import Module, Signal

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git
from nmutil.sim_tmp_alternative import Simulator, Settle


def get_cu_inputs(dec2, sim):
    """naming (res) must conform to ALUFunctionUnit input regspec
    """
    res = {}

    yield from ALUHelpers.get_sim_int_ra(res, sim, dec2)  # RA
    yield from ALUHelpers.get_sim_int_rb(res, sim, dec2)  # RB
    yield from ALUHelpers.get_rd_sim_xer_ca(res, sim, dec2)  # XER.ca
    yield from ALUHelpers.get_sim_xer_so(res, sim, dec2)  # XER.so

    print("alu get_cu_inputs", res)

    return res


def set_alu_inputs(alu, dec2, sim):
    # TODO: see https://bugs.libre-soc.org/show_bug.cgi?id=305#c43
    # detect the immediate here (with m.If(self.i.ctx.op.imm_data.imm_ok))
    # and place it into data_i.b

    inp = yield from get_cu_inputs(dec2, sim)
    yield from ALUHelpers.set_int_ra(alu, dec2, inp)
    yield from ALUHelpers.set_int_rb(alu, dec2, inp)

    yield from ALUHelpers.set_xer_ca(alu, dec2, inp)
    yield from ALUHelpers.set_xer_so(alu, dec2, inp)


class ALUTestCase(TestAccumulatorBase):

    def case_1_regression(self):
        lst = [f"extsw 3, 1"]
        initial_regs = [0] * 32
        initial_regs[1] = 0xb6a1fc6c8576af91
        self.add_case(Program(lst, bigendian), initial_regs)
        lst = [f"subf 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x3d7f3f7ca24bac7b
        initial_regs[2] = 0xf6b2ac5e13ee15c2
        self.add_case(Program(lst, bigendian), initial_regs)
        lst = [f"subf 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x833652d96c7c0058
        initial_regs[2] = 0x1c27ecff8a086c1a
        self.add_case(Program(lst, bigendian), initial_regs)
        lst = [f"extsb 3, 1"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x7f9497aaff900ea0
        self.add_case(Program(lst, bigendian), initial_regs)
        lst = [f"add. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0xc523e996a8ff6215
        initial_regs[2] = 0xe1e5b9cc9864c4a8
        self.add_case(Program(lst, bigendian), initial_regs)
        lst = [f"add 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x2e08ae202742baf8
        initial_regs[2] = 0x86c43ece9efe5baa
        self.add_case(Program(lst, bigendian), initial_regs)

    def case_rand(self):
        insns = ["add", "add.", "subf"]
        for i in range(40):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1 << 64)-1)
            initial_regs[2] = random.randint(0, (1 << 64)-1)
            self.add_case(Program(lst, bigendian), initial_regs)

    def case_addme_ca_0(self):
        insns = ["addme", "addme.", "addmeo", "addmeo."]
        for choice in insns:
            lst = [f"{choice} 6, 16"]
            for value in [0x7ffffffff,
                          0xffff80000]:
                initial_regs = [0] * 32
                initial_regs[16] = value
                initial_sprs = {}
                xer = SelectableInt(0, 64)
                xer[XER_bits['CA']] = 0
                initial_sprs[special_sprs['XER']] = xer
                self.add_case(Program(lst, bigendian),
                              initial_regs, initial_sprs)

    def case_addme_ca_1(self):
        insns = ["addme", "addme.", "addmeo", "addmeo."]
        for choice in insns:
            lst = [f"{choice} 6, 16"]
            for value in [0x7ffffffff, # fails, bug #476
                          0xffff80000]:
                initial_regs = [0] * 32
                initial_regs[16] = value
                initial_sprs = {}
                xer = SelectableInt(0, 64)
                xer[XER_bits['CA']] = 1
                initial_sprs[special_sprs['XER']] = xer
                self.add_case(Program(lst, bigendian),
                              initial_regs, initial_sprs)

    def case_addme_ca_so_3(self):
        """bug where SO does not get passed through to CR0
        """
        lst = ["addme. 6, 16"]
        initial_regs = [0] * 32
        initial_regs[16] = 0x7ffffffff
        initial_sprs = {}
        xer = SelectableInt(0, 64)
        xer[XER_bits['CA']] = 1
        xer[XER_bits['SO']] = 1
        initial_sprs[special_sprs['XER']] = xer
        self.add_case(Program(lst, bigendian),
                      initial_regs, initial_sprs)

    def case_addze(self):
        insns = ["addze", "addze.", "addzeo", "addzeo."]
        for choice in insns:
            lst = [f"{choice} 6, 16"]
            initial_regs = [0] * 32
            initial_regs[16] = 0x00ff00ff00ff0080
            self.add_case(Program(lst, bigendian), initial_regs)

        self.add_case(Program(lst, bigendian), initial_regs)

    def case_addis_nonzero_r0_regression(self):
        lst = [f"addis 3, 0, 1"]
        print(lst)
        initial_regs = [0] * 32
        initial_regs[0] = 5
        self.add_case(Program(lst, bigendian), initial_regs)

    def case_addis_nonzero_r0(self):
        for i in range(10):
            imm = random.randint(-(1 << 15), (1 << 15)-1)
            lst = [f"addis 3, 0, {imm}"]
            print(lst)
            initial_regs = [0] * 32
            initial_regs[0] = random.randint(0, (1 << 64)-1)
            self.add_case(Program(lst, bigendian), initial_regs)

    def case_rand_imm(self):
        insns = ["addi", "addis", "subfic"]
        for i in range(10):
            choice = random.choice(insns)
            imm = random.randint(-(1 << 15), (1 << 15)-1)
            lst = [f"{choice} 3, 1, {imm}"]
            print(lst)
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1 << 64)-1)
            self.add_case(Program(lst, bigendian), initial_regs)

    def case_0_adde(self):
        lst = ["adde. 5, 6, 7"]
        for i in range(10):
            initial_regs = [0] * 32
            initial_regs[6] = random.randint(0, (1 << 64)-1)
            initial_regs[7] = random.randint(0, (1 << 64)-1)
            initial_sprs = {}
            xer = SelectableInt(0, 64)
            xer[XER_bits['CA']] = 1
            initial_sprs[special_sprs['XER']] = xer
            self.add_case(Program(lst, bigendian),
                          initial_regs, initial_sprs)

    def case_cmp(self):
        lst = ["subf. 1, 6, 7",
               "cmp cr2, 1, 6, 7"]
        initial_regs = [0] * 32
        initial_regs[6] = 0x10
        initial_regs[7] = 0x05
        self.add_case(Program(lst, bigendian), initial_regs, {})

    def case_cmp2(self):
        lst = ["cmp cr2, 0, 2, 3"]
        initial_regs = [0] * 32
        initial_regs[2] = 0xffffffffaaaaaaaa
        initial_regs[3] = 0x00000000aaaaaaaa
        self.add_case(Program(lst, bigendian), initial_regs, {})

        lst = ["cmp cr2, 0, 4, 5"]
        initial_regs = [0] * 32
        initial_regs[4] = 0x00000000aaaaaaaa
        initial_regs[5] = 0xffffffffaaaaaaaa
        self.add_case(Program(lst, bigendian), initial_regs, {})

    def case_cmp3(self):
        lst = ["cmp cr2, 1, 2, 3"]
        initial_regs = [0] * 32
        initial_regs[2] = 0xffffffffaaaaaaaa
        initial_regs[3] = 0x00000000aaaaaaaa
        self.add_case(Program(lst, bigendian), initial_regs, {})

        lst = ["cmp cr2, 1, 4, 5"]
        initial_regs = [0] * 32
        initial_regs[4] = 0x00000000aaaaaaaa
        initial_regs[5] = 0xffffffffaaaaaaaa
        self.add_case(Program(lst, bigendian), initial_regs, {})

    def case_cmpl_microwatt_0(self):
        """microwatt 1.bin:
           115b8:   40 50 d1 7c     .long 0x7cd15040 # cmpl 6, 0, 17, 10
            register_file.vhdl: Reading GPR 11 000000000001C026
            register_file.vhdl: Reading GPR 0A FEDF3FFF0001C025
            cr_file.vhdl: Reading CR 35055050
            cr_file.vhdl: Writing 35055058 to CR mask 01 35055058
        """

        lst = ["cmpl 6, 0, 17, 10"]
        initial_regs = [0] * 32
        initial_regs[0x11] = 0x1c026
        initial_regs[0xa] =  0xFEDF3FFF0001C025
        XER = 0xe00c0000
        CR = 0x35055050

        self.add_case(Program(lst, bigendian), initial_regs,
                                initial_sprs = {'XER': XER},
                                initial_cr = CR)

    def case_cmpl_microwatt_0_disasm(self):
        """microwatt 1.bin: disassembled version
           115b8:   40 50 d1 7c     .long 0x7cd15040 # cmpl 6, 0, 17, 10
            register_file.vhdl: Reading GPR 11 000000000001C026
            register_file.vhdl: Reading GPR 0A FEDF3FFF0001C025
            cr_file.vhdl: Reading CR 35055050
            cr_file.vhdl: Writing 35055058 to CR mask 01 35055058
        """

        dis = ["cmpl 6, 0, 17, 10"]
        lst = bytes([0x40, 0x50, 0xd1, 0x7c]) # 0x7cd15040
        initial_regs = [0] * 32
        initial_regs[0x11] = 0x1c026
        initial_regs[0xa] =  0xFEDF3FFF0001C025
        XER = 0xe00c0000
        CR = 0x35055050

        p = Program(lst, bigendian)
        p.assembly = '\n'.join(dis)+'\n'
        self.add_case(p, initial_regs,
                                initial_sprs = {'XER': XER},
                                initial_cr = CR)

    def case_cmplw_microwatt_1(self):
        """microwatt 1.bin:
           10d94:   40 20 96 7c     cmplw   cr1,r22,r4
            gpr: 00000000ffff6dc1 <- r4
            gpr: 0000000000000000 <- r22
        """

        lst = ["cmpl 1, 0, 22, 4"]
        initial_regs = [0] * 32
        initial_regs[4] = 0xffff6dc1
        initial_regs[22] = 0
        XER = 0xe00c0000
        CR = 0x50759999

        self.add_case(Program(lst, bigendian), initial_regs,
                                initial_sprs = {'XER': XER},
                                initial_cr = CR)

    def case_cmpli_microwatt(self):
        """microwatt 1.bin: cmpli
           123ac:   9c 79 8d 2a     cmpli   cr5,0,r13,31132
            gpr: 00000000301fc7a7 <- r13
            cr : 0000000090215393
            xer: so 1 ca 0 32 0 ov 0 32 0

        """

        lst = ["cmpli 5, 0, 13, 31132"]
        initial_regs = [0] * 32
        initial_regs[13] = 0x301fc7a7
        XER = 0xe00c0000
        CR = 0x90215393

        self.add_case(Program(lst, bigendian), initial_regs,
                                initial_sprs = {'XER': XER},
                                initial_cr = CR)

    def case_extsb(self):
        insns = ["extsb", "extsh", "extsw"]
        for i in range(10):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1"]
            print(lst)
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1 << 64)-1)
            self.add_case(Program(lst, bigendian), initial_regs)

    def case_cmpeqb(self):
        lst = ["cmpeqb cr1, 1, 2"]
        for i in range(20):
            initial_regs = [0] * 32
            initial_regs[1] = i
            initial_regs[2] = 0x0001030507090b0f
            self.add_case(Program(lst, bigendian), initial_regs, {})

    def case_ilang(self):
        pspec = ALUPipeSpec(id_wid=2)
        alu = ALUBasePipe(pspec)
        vl = rtlil.convert(alu, ports=alu.ports())
        with open("alu_pipeline.il", "w") as f:
            f.write(vl)


class TestRunner(unittest.TestCase):

    def execute(self, alu,instruction, pdecode2, test):
        program = test.program
        sim = ISA(pdecode2, test.regs, test.sprs, test.cr,
                  test.mem, test.msr,
                  bigendian=bigendian)
        gen = program.generate_instructions()
        instructions = list(zip(gen, program.assembly.splitlines()))

        index = sim.pc.CIA.value//4
        while index < len(instructions):
            ins, code = instructions[index]

            print("instruction: 0x{:X}".format(ins & 0xffffffff))
            print(code)
            if 'XER' in sim.spr:
                so = 1 if sim.spr['XER'][XER_bits['SO']] else 0
                ov = 1 if sim.spr['XER'][XER_bits['OV']] else 0
                ov32 = 1 if sim.spr['XER'][XER_bits['OV32']] else 0
                print("before: so/ov/32", so, ov, ov32)

            # ask the decoder to decode this binary data (endian'd)
            # little / big?
            yield pdecode2.dec.bigendian.eq(bigendian)
            yield instruction.eq(ins)          # raw binary instr.
            yield Settle()
            fn_unit = yield pdecode2.e.do.fn_unit
            asmcode = yield pdecode2.e.asmcode
            dec_asmcode = yield pdecode2.dec.op.asmcode
            print ("asmcode", asmcode, dec_asmcode)
            self.assertEqual(fn_unit, Function.ALU.value)
            yield from set_alu_inputs(alu, pdecode2, sim)

            # set valid for one cycle, propagate through pipeline...
            yield alu.p.valid_i.eq(1)
            yield
            yield alu.p.valid_i.eq(0)

            opname = code.split(' ')[0]
            yield from sim.call(opname)
            index = sim.pc.CIA.value//4

            vld = yield alu.n.valid_o
            while not vld:
                yield
                vld = yield alu.n.valid_o
            yield

            yield from self.check_alu_outputs(alu, pdecode2, sim, code)
            yield Settle()

    def test_it(self):
        test_data = ALUTestCase().test_data
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        fn_name = "ALU"
        opkls = ALUPipeSpec.opsubsetkls

        pdecode = create_pdecode()
        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode, opkls, fn_name)
        pdecode = pdecode2.dec

        pspec = ALUPipeSpec(id_wid=2)
        m.submodules.alu = alu = ALUBasePipe(pspec)

        comb += alu.p.data_i.ctx.op.eq_from_execute1(pdecode2.e)
        comb += alu.n.ready_i.eq(1)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)

        sim.add_clock(1e-6)

        def process():
            for test in test_data:
                print(test.name)
                program = test.program
                with self.subTest(test.name):
                    yield from self.execute(alu, instruction, pdecode2, test)

        sim.add_sync_process(process)
        with sim.write_vcd("alu_simulator.vcd"):
            sim.run()

    def check_alu_outputs(self, alu, dec2, sim, code):

        rc = yield dec2.e.do.rc.rc
        cridx_ok = yield dec2.e.write_cr.ok
        cridx = yield dec2.e.write_cr.data

        print("check extra output", repr(code), cridx_ok, cridx)
        if rc:
            self.assertEqual(cridx, 0, code)

        oe = yield dec2.e.do.oe.oe
        oe_ok = yield dec2.e.do.oe.ok
        if not oe or not oe_ok:
            # if OE not enabled, XER SO and OV must correspondingly be false
            so_ok = yield alu.n.data_o.xer_so.ok
            ov_ok = yield alu.n.data_o.xer_ov.ok
            self.assertEqual(so_ok, False, code)
            self.assertEqual(ov_ok, False, code)

        sim_o = {}
        res = {}

        yield from ALUHelpers.get_cr_a(res, alu, dec2)
        yield from ALUHelpers.get_xer_ov(res, alu, dec2)
        yield from ALUHelpers.get_xer_ca(res, alu, dec2)
        yield from ALUHelpers.get_int_o(res, alu, dec2)
        yield from ALUHelpers.get_xer_so(res, alu, dec2)

        yield from ALUHelpers.get_sim_int_o(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_sim_cr_a(sim_o, sim, dec2)
        yield from ALUHelpers.get_sim_xer_ov(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_sim_xer_ca(sim_o, sim, dec2)
        yield from ALUHelpers.get_sim_xer_so(sim_o, sim, dec2)

        ALUHelpers.check_cr_a(self, res, sim_o, "CR%d %s" % (cridx, code))
        ALUHelpers.check_xer_ov(self, res, sim_o, code)
        ALUHelpers.check_xer_ca(self, res, sim_o, code)
        ALUHelpers.check_int_o(self, res, sim_o, code)
        ALUHelpers.check_xer_so(self, res, sim_o, code)


if __name__ == "__main__":
    unittest.main()
