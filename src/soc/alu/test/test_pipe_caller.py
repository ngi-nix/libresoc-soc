from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmigen.test.utils import FHDLTestCase
from nmigen.cli import rtlil
import unittest
from soc.decoder.isa.caller import ISACaller, special_sprs
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.decoder.power_enums import (XER_bits)
from soc.decoder.selectable_int import SelectableInt
from soc.simulator.program import Program
from soc.decoder.isa.all import ISA


from soc.alu.pipeline import ALUBasePipe
from soc.alu.alu_input_record import CompALUOpSubset
from soc.alu.pipe_data import ALUPipeSpec
import random

def get_rec_width(rec):
    recwidth = 0
    # Setup random inputs for dut.op
    for p in rec.ports():
        width = p.width
        recwidth += width
    return recwidth

def set_alu_inputs(alu, dec2, sim):
    inputs = []
    reg3_ok = yield dec2.e.read_reg3.ok
    if reg3_ok:
        reg3_sel = yield dec2.e.read_reg3.data
        inputs.append(sim.gpr(reg3_sel).value)
    reg1_ok = yield dec2.e.read_reg1.ok
    if reg1_ok:
        reg1_sel = yield dec2.e.read_reg1.data
        inputs.append(sim.gpr(reg1_sel).value)
    reg2_ok = yield dec2.e.read_reg2.ok
    if reg2_ok:
        reg2_sel = yield dec2.e.read_reg2.data
        inputs.append(sim.gpr(reg2_sel).value)

    print(inputs)

    if len(inputs) == 0:
        yield alu.p.data_i.a.eq(0)
        yield alu.p.data_i.b.eq(0)
    if len(inputs) == 1:
        yield alu.p.data_i.a.eq(inputs[0])
        yield alu.p.data_i.b.eq(0)
    if len(inputs) == 2:
        yield alu.p.data_i.a.eq(inputs[0])
        yield alu.p.data_i.b.eq(inputs[1])

def set_extra_alu_inputs(alu, dec2, sim):
    carry = 1 if sim.spr['XER'][XER_bits['CA']] else 0
    yield alu.p.data_i.carry_in.eq(carry)
    so = 1 if sim.spr['XER'][XER_bits['SO']] else 0
    yield alu.p.data_i.so.eq(so)
    

class ALUTestCase(FHDLTestCase):
    def run_tst(self, program, initial_regs, initial_sprs):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)

        rec = CompALUOpSubset()

        pspec = ALUPipeSpec(id_wid=2, op_wid=get_rec_width(rec))
        m.submodules.alu = alu = ALUBasePipe(pspec)

        comb += alu.p.data_i.ctx.op.eq_from_execute1(pdecode2.e)
        comb += alu.p.valid_i.eq(1)
        comb += alu.n.ready_i.eq(1)
        simulator = ISA(pdecode2, initial_regs, initial_sprs)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)
        gen = program.generate_instructions()

        sim.add_clock(1e-6)
        def process():
            instructions = list(zip(gen, program.assembly.splitlines()))

            index = simulator.pc.CIA.value//4
            while index < len(instructions):
                ins, code = instructions[index]

                print("0x{:X}".format(ins & 0xffffffff))
                print(code)

                # ask the decoder to decode this binary data (endian'd)
                yield pdecode2.dec.bigendian.eq(0)  # little / big?
                yield instruction.eq(ins)          # raw binary instr.
                yield Settle()
                yield from set_alu_inputs(alu, pdecode2, simulator)
                yield from set_extra_alu_inputs(alu, pdecode2, simulator)
                yield 
                opname = code.split(' ')[0]
                yield from simulator.call(opname)
                index = simulator.pc.CIA.value//4

                vld = yield alu.n.valid_o
                while not vld:
                    yield
                    vld = yield alu.n.valid_o
                yield
                alu_out = yield alu.n.data_o.o
                out_reg_valid = yield pdecode2.e.write_reg.ok
                if out_reg_valid:
                    write_reg_idx = yield pdecode2.e.write_reg.data
                    expected = simulator.gpr(write_reg_idx).value
                    print(f"expected {expected:x}, actual: {alu_out:x}")
                    self.assertEqual(expected, alu_out)
                yield from self.check_extra_alu_outputs(alu, pdecode2,
                                                        simulator)

        sim.add_sync_process(process)
        with sim.write_vcd("simulator.vcd", "simulator.gtkw",
                           traces=[]):
            sim.run()
        return simulator
    def check_extra_alu_outputs(self, alu, dec2, sim):
        rc = yield dec2.e.rc.data
        if rc:
            cr_expected = sim.crl[0].get_range().value
            cr_actual = yield alu.n.data_o.cr0
            self.assertEqual(cr_expected, cr_actual)

    def run_tst_program(self, prog, initial_regs=[0] * 32, initial_sprs={}):
        simulator = self.run_tst(prog, initial_regs, initial_sprs)
        simulator.gpr.dump()
        return simulator

    def test_rand(self):
        insns = ["add", "add.", "and", "or", "xor", "subf"]
        for i in range(40):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1<<64)-1)
            initial_regs[2] = random.randint(0, (1<<64)-1)
            with Program(lst) as program:
                sim = self.run_tst_program(program, initial_regs)

    def test_rand_imm(self):
        insns = ["addi", "addis", "subfic"]
        for i in range(10):
            choice = random.choice(insns)
            imm = random.randint(-(1<<15), (1<<15)-1)
            lst = [f"{choice} 3, 1, {imm}"]
            print(lst)
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1<<64)-1)
            with Program(lst) as program:
                sim = self.run_tst_program(program, initial_regs)

    def test_rand_imm_logical(self):
        insns = ["andi.", "andis.", "ori", "oris", "xori", "xoris"]
        for i in range(10):
            choice = random.choice(insns)
            imm = random.randint(0, (1<<16)-1)
            lst = [f"{choice} 3, 1, {imm}"]
            print(lst)
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1<<64)-1)
            with Program(lst) as program:
                sim = self.run_tst_program(program, initial_regs)

    def test_shift(self):
        insns = ["slw", "sld", "srw", "srd", "sraw", "srad"]
        for i in range(20):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1<<64)-1)
            initial_regs[2] = random.randint(0, 63)
            print(initial_regs[1], initial_regs[2])
            with Program(lst) as program:
                sim = self.run_tst_program(program, initial_regs)


    def test_shift_arith(self):
        lst = ["sraw 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = random.randint(0, (1<<64)-1)
        initial_regs[2] = random.randint(0, 63)
        print(initial_regs[1], initial_regs[2])
        with Program(lst) as program:
            sim = self.run_tst_program(program, initial_regs)

    def test_rlwinm(self):
        for i in range(10):
            mb = random.randint(0,31)
            me = random.randint(0,31)
            sh = random.randint(0,31)
            lst = [f"rlwinm 3, 1, {mb}, {me}, {sh}"]
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1<<64)-1)
            with Program(lst) as program:
                sim = self.run_tst_program(program, initial_regs)

    def test_rlwimi(self):
        lst = ["rlwimi 3, 1, 5, 20, 6"]
        initial_regs = [0] * 32
        initial_regs[1] = 0xdeadbeef
        initial_regs[3] = 0x12345678
        with Program(lst) as program:
            sim = self.run_tst_program(program, initial_regs)

    def test_rlwnm(self):
        lst = ["rlwnm 3, 1, 2, 20, 6"]
        initial_regs = [0] * 32
        initial_regs[1] = random.randint(0, (1<<64)-1)
        initial_regs[2] = random.randint(0, 63)
        with Program(lst) as program:
            sim = self.run_tst_program(program, initial_regs)
        
    def test_adde(self):
        lst = ["adde. 5, 6, 7"]
        initial_regs = [0] * 32
        initial_regs[6] = random.randint(0, (1<<64)-1)
        initial_regs[7] = random.randint(0, (1<<64)-1)
        initial_sprs = {}
        xer = SelectableInt(0, 64)
        xer[XER_bits['CA']] = 1
        initial_sprs[special_sprs['XER']] = xer
        with Program(lst) as program:
            sim = self.run_tst_program(program, initial_regs, initial_sprs)

    def test_ilang(self):
        rec = CompALUOpSubset()

        pspec = ALUPipeSpec(id_wid=2, op_wid=get_rec_width(rec))
        alu = ALUBasePipe(pspec)
        vl = rtlil.convert(alu, ports=[])
        with open("pipeline.il", "w") as f:
            f.write(vl)

if __name__ == "__main__":
    unittest.main()
