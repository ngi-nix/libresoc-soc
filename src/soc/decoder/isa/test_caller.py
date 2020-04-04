from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay
from nmigen.test.utils import FHDLTestCase
import unittest
from soc.decoder.isa.caller import ISACaller
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.simulator.program import Program
from soc.simulator.qemu import run_program
from soc.decoder.isa.caller import ISACaller, inject
from soc.decoder.helpers import (EXTS64, EXTZ64, ROTL64, ROTL32, MASK,)
from soc.decoder.selectable_int import SelectableInt
from soc.decoder.selectable_int import selectconcat as concat
from soc.decoder.orderedset import OrderedSet

class fixedarith(ISACaller):

    @inject
    def op_addi(self, RA):
        if RA == 0:
            RT = EXTS(SI)
        else:
            RT = RA + EXTS(SI)
        return (RT,)

    instrs = {}
    instrs['addi'] = (op_addi, OrderedSet(['RA']),
                OrderedSet(), OrderedSet(['RT']))



class Register:
    def __init__(self, num):
        self.num = num


class DecoderTestCase(FHDLTestCase):

    def run_tst(self, generator):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()
        simulator = ISACaller(pdecode, [0] * 32)

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)
        gen = generator.generate_instructions()

        def process():
            for ins in gen:

                print("0x{:X}".format(ins & 0xffffffff))

                # ask the decoder to decode this binary data (endian'd)
                yield pdecode2.dec.bigendian.eq(0)  # little / big?
                yield instruction.eq(ins)          # raw binary instr.
                yield Delay(1e-6)
                yield from simulator.execute_op(pdecode2)

        sim.add_process(process)
        with sim.write_vcd("simulator.vcd", "simulator.gtkw",
                           traces=[]):
            sim.run()
        return simulator

    def test_addi(self):
        lst = ["addi 1, 0, 0x1234",]
        with Program(lst) as program:
            self.run_test_program(program)

    def run_test_program(self, prog):
        simulator = self.run_tst(prog)
        print(simulator.gpr)

if __name__ == "__main__":
    unittest.main()
