from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay
from nmigen.test.utils import FHDLTestCase
import unittest
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_enums import (Function, InternalOp,
                                     In1Sel, In2Sel, In3Sel,
                                     OutSel, RC, LdstLen, CryIn,
                                     single_bit_flags, Form,
                                     get_signal_name, get_csv)
from soc.decoder.power_decoder2 import (PowerDecode2)
import tempfile
import subprocess
import struct
import random

ops = {
    InternalOp.OP_ADD: "add",
    InternalOp.OP_AND: "and",
    InternalOp.OP_OR: "or"}


class Register:
    def __init__(self, num):
        self.num = num


class DecoderTestCase(FHDLTestCase):
    def generate_opcode_string(self, internalop, r1, r2, op3):
        opcodestr = ops[internalop]
        if isinstance(op3, Register):
            immstring = ""
            op3str = op3.num
        else:
            immstring = "i"
            op3str = str(op3)
        string = "{}{} {}, {}, {}\n".format(opcodestr,
                                            immstring,
                                            r1.num,
                                            r2.num,
                                            op3str)
        return string

    def get_assembled_instruction(self, instruction):
        with tempfile.NamedTemporaryFile(suffix=".o") as outfile:
            args = ["powerpc64-linux-gnu-as",
                    "-o",
                    outfile.name]
            p = subprocess.Popen(args, stdin=subprocess.PIPE)
            p.communicate(instruction.encode('utf-8'))
            assert(p.wait() == 0)

            with tempfile.NamedTemporaryFile(suffix=".bin") as binfile:
                args = ["powerpc64-linux-gnu-objcopy",
                        "-O", "binary",
                        outfile.name,
                        binfile.name]
                subprocess.check_output(args)
                binary = struct.unpack('>i', binfile.read(4))[0]
                return binary

    def test_decoder(self):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)
        comb += pdecode2.dec.opcode_in.eq(instruction)

        sim = Simulator(m)

        def process():
            for i in range(10):
                opcode = random.choice(list(ops.keys()))
                r1 = Register(random.randrange(32))
                r2 = Register(random.randrange(32))
                r3 = Register(random.randrange(32))

                instruction_str = self.generate_opcode_string(
                    opcode, r1, r2, r3)
                print("instr", instruction_str.strip())
                instruction_bin = self.get_assembled_instruction(
                    instruction_str)
                print("code", hex(instruction_bin), bin(instruction_bin))

                yield instruction.eq(instruction_bin)
                yield Delay(1e-6)

                r1sel = yield pdecode2.e.write_reg.data
                r3sel = yield pdecode2.e.read_reg2.data

                # For some reason r2 gets decoded either in read_reg1
                # or read_reg3
                form = yield pdecode2.dec.op.form
                if form == Form.X.value:
                    r2sel = yield pdecode2.e.read_reg3.data
                else:
                    r2sel = yield pdecode2.e.read_reg1.data
                assert(r1sel == r1.num)
                assert(r3sel == r3.num)
                assert(r2sel == r2.num)

        sim.add_process(process)
        with sim.write_vcd("gas.vcd", "gas.gtkw", traces=[pdecode2.ports()]):
            sim.run()


if __name__ == "__main__":
    unittest.main()
