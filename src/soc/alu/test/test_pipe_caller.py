from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay
from nmigen.test.utils import FHDLTestCase
from nmigen.cli import rtlil
import unittest
from soc.decoder.isa.caller import ISACaller
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
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



class ALUTestCase(FHDLTestCase):
    def run_tst(self, program, initial_regs):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)

        rec = CompALUOpSubset()

        pspec = ALUPipeSpec(id_wid=2, op_wid=get_rec_width(rec))
        m.submodules.alu = alu = ALUBasePipe(pspec)

        comb += alu.p.data_i.ctx.op.eq_from_execute1(pdecode2.e)
        comb += alu.p.data_i.a.eq(initial_regs[1])
        comb += alu.p.data_i.b.eq(initial_regs[2])
        comb += alu.p.valid_i.eq(1)
        comb += alu.n.ready_i.eq(1)
        simulator = ISA(pdecode2, initial_regs)
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
                self.assertEqual(simulator.gpr(3).value, alu_out)

        sim.add_sync_process(process)
        with sim.write_vcd("simulator.vcd", "simulator.gtkw",
                           traces=[]):
            sim.run()
        return simulator

    def run_tst_program(self, prog, initial_regs=[0] * 32):
        simulator = self.run_tst(prog, initial_regs)
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

    def test_ilang(self):
        rec = CompALUOpSubset()

        pspec = ALUPipeSpec(id_wid=2, op_wid=get_rec_width(rec))
        alu = ALUBasePipe(pspec)
        vl = rtlil.convert(alu, ports=[])
        with open("pipeline.il", "w") as f:
            f.write(vl)

if __name__ == "__main__":
    unittest.main()
