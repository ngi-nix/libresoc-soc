from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay
from nmigen.test.utils import FHDLTestCase
import unittest
from soc.simulator.internalop_sim import InternalOpSimulator
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_enums import (Function, InternalOp,
                                     In1Sel, In2Sel, In3Sel,
                                     OutSel, RC, LdstLen, CryIn,
                                     single_bit_flags, Form, SPR,
                                     get_signal_name, get_csv)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.simulator.gas import get_assembled_instruction


class Register:
    def __init__(self, num):
        self.num = num


class InstrList:
    def __init__(self, lst):
        self.instrs = [x + "\n" for x in lst]

    def generate_instructions(self):
        return iter(self.instrs)


class DecoderTestCase(FHDLTestCase):

    def run_tst(self, generator, simulator):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)
        gen = generator.generate_instructions()

        def process():
            for ins in gen:
                print("instr", ins.strip())

                # turn the instruction into binary data (endian'd)
                ibin = get_assembled_instruction(ins, 0)

                # ask the decoder to decode this binary data (endian'd)
                yield pdecode2.dec.bigendian.eq(0)  # little / big?
                yield instruction.eq(ibin)          # raw binary instr.
                yield Delay(1e-6)
                yield from simulator.execute_op(pdecode2)

        sim.add_process(process)
        with sim.write_vcd("simulator.vcd", "simulator.gtkw",
                           traces=[pdecode2.ports()]):
            sim.run()

    def test_example(self):
        lst = ["addi 1, 0, 0x1234",
               "addi 2, 0, 0x5678",
               "add  3, 1, 2",
               "and  4, 1, 2"]
        gen = InstrList(lst)

        simulator = InternalOpSimulator()

        self.run_tst(gen, simulator)
        simulator.regfile.assert_gprs(
            {1: 0x1234,
             2: 0x5678,
             3: 0x68ac,
             4: 0x1230})

    def test_ldst(self):
        lst = ["addi 1, 0, 0x1234",
               "addi 2, 0, 0x5678",
               "stw  1, 0(2)",
               "lwz  3, 0(2)"]
        gen = InstrList(lst)

        simulator = InternalOpSimulator()

        self.run_tst(gen, simulator)
        simulator.regfile.assert_gprs(
            {1: 0x1234,
             2: 0x5678,
             3: 0x1234})


if __name__ == "__main__":
    unittest.main()
