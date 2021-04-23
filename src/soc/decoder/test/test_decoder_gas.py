from nmigen import Module, Signal

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git
from nmutil.sim_tmp_alternative import Simulator, Delay

from nmutil.formaltest import FHDLTestCase
import unittest
from openpower.decoder.power_decoder import (create_pdecode)
from openpower.decoder.power_enums import (Function, MicrOp,
                                     In1Sel, In2Sel, In3Sel,
                                     OutSel, RC, LdstLen, CryIn,
                                     single_bit_flags, Form, SPR,
                                     get_signal_name, get_csv)
from openpower.decoder.power_decoder2 import (PowerDecode2)
from openpower.simulator.gas import get_assembled_instruction
import random


class Register:
    def __init__(self, num):
        self.num = num


class Checker:
    def __init__(self):
        self.imm = 0

    def get_imm(self, in2_sel):
        if in2_sel == In2Sel.CONST_UI.value:
            return self.imm & 0xffff
        if in2_sel == In2Sel.CONST_UI_HI.value:
            return (self.imm & 0xffff) << 16
        if in2_sel == In2Sel.CONST_SI.value:
            sign_bit = 1 << 15
            return (self.imm & (sign_bit-1)) - (self.imm & sign_bit)
        if in2_sel == In2Sel.CONST_SI_HI.value:
            imm = self.imm << 16
            sign_bit = 1 << 31
            return (imm & (sign_bit-1)) - (imm & sign_bit)


class RegRegOp:
    def __init__(self):
        self.ops = {
            "add": MicrOp.OP_ADD,
            "and": MicrOp.OP_AND,
            "or": MicrOp.OP_OR,
            "add.": MicrOp.OP_ADD,
            "lwzx": MicrOp.OP_LOAD,
            "stwx": MicrOp.OP_STORE,
        }
        self.opcodestr = random.choice(list(self.ops.keys()))
        self.opcode = self.ops[self.opcodestr]
        self.r1 = Register(random.randrange(32))
        self.r2 = Register(random.randrange(32))
        self.r3 = Register(random.randrange(32))

    def generate_instruction(self):
        string = "{} {}, {}, {}\n".format(self.opcodestr,
                                          self.r1.num,
                                          self.r2.num,
                                          self.r3.num)
        return string

    def check_results(self, pdecode2):
        if self.opcode == MicrOp.OP_STORE:
            r1sel = yield pdecode2.e.read_reg3.data
        else:
            r1sel = yield pdecode2.e.write_reg.data

        r3sel = yield pdecode2.e.read_reg2.data

        # For some reason r2 gets decoded either in read_reg1
        # or read_reg3
        out_sel = yield pdecode2.dec.op.out_sel
        if out_sel == OutSel.RA.value:
            r2sel = yield pdecode2.e.read_reg3.data
        else:
            r2sel = yield pdecode2.e.read_reg1.data
        assert(r1sel == self.r1.num)
        assert(r3sel == self.r3.num)
        assert(r2sel == self.r2.num)

        opc_out = yield pdecode2.dec.op.internal_op
        assert(opc_out == self.opcode.value)
        # check RC value (the dot in the instruction)
        rc = yield pdecode2.e.rc.data
        if '.' in self.opcodestr:
            assert(rc == 1)
        else:
            assert(rc == 0)


class RegImmOp(Checker):
    def __init__(self):
        super().__init__()
        self.ops = {
            "addi": MicrOp.OP_ADD,
            "addis": MicrOp.OP_ADD,
            "andi.": MicrOp.OP_AND,
            "ori": MicrOp.OP_OR,
        }
        self.opcodestr = random.choice(list(self.ops.keys()))
        self.opcode = self.ops[self.opcodestr]
        self.r1 = Register(random.randrange(32))
        self.r2 = Register(random.randrange(32))
        self.imm = random.randrange(32767)

    def generate_instruction(self):
        string = "{} {}, {}, {}\n".format(self.opcodestr,
                                          self.r1.num,
                                          self.r2.num,
                                          self.imm)
        return string

    def check_results(self, pdecode2):
        print("Check")
        r1sel = yield pdecode2.e.write_reg.data
        # For some reason r2 gets decoded either in read_reg1
        # or read_reg3
        out_sel = yield pdecode2.dec.op.out_sel
        if out_sel == OutSel.RA.value:
            r2sel = yield pdecode2.e.read_reg3.data
        else:
            r2sel = yield pdecode2.e.read_reg1.data
        assert(r1sel == self.r1.num)
        assert(r2sel == self.r2.num)

        imm = yield pdecode2.e.imm_data.data
        in2_sel = yield pdecode2.dec.op.in2_sel
        imm_expected = self.get_imm(in2_sel)
        msg = "imm: got {:x}, expected {:x}".format(imm, imm_expected)
        assert imm == imm_expected, msg

        rc = yield pdecode2.e.rc.data
        if '.' in self.opcodestr:
            assert(rc == 1)
        else:
            assert(rc == 0)


class LdStOp(Checker):
    def __init__(self):
        super().__init__()
        self.ops = {
            "lwz": MicrOp.OP_LOAD,
            "stw": MicrOp.OP_STORE,
            "lwzu": MicrOp.OP_LOAD,
            "stwu": MicrOp.OP_STORE,
            "lbz": MicrOp.OP_LOAD,
            "lhz": MicrOp.OP_LOAD,
            "stb": MicrOp.OP_STORE,
            "sth": MicrOp.OP_STORE,
        }
        self.opcodestr = random.choice(list(self.ops.keys()))
        self.opcode = self.ops[self.opcodestr]
        self.r1 = Register(random.randrange(32))
        self.r2 = Register(random.randrange(1, 32))
        while self.r2.num == self.r1.num:
            self.r2 = Register(random.randrange(1, 32))
        self.imm = random.randrange(32767)

    def generate_instruction(self):
        string = "{} {}, {}({})\n".format(self.opcodestr,
                                          self.r1.num,
                                          self.imm,
                                          self.r2.num)
        return string

    def check_results(self, pdecode2):
        print("Check")
        r2sel = yield pdecode2.e.read_reg1.data
        if self.opcode == MicrOp.OP_STORE:
            r1sel = yield pdecode2.e.read_reg3.data
        else:
            r1sel = yield pdecode2.e.write_reg.data
        assert(r1sel == self.r1.num)
        assert(r2sel == self.r2.num)

        imm = yield pdecode2.e.imm_data.data
        in2_sel = yield pdecode2.dec.op.in2_sel
        assert(imm == self.get_imm(in2_sel))

        update = yield pdecode2.e.update
        if "u" in self.opcodestr:
            assert(update == 1)
        else:
            assert(update == 0)

        size = yield pdecode2.e.data_len
        if "w" in self.opcodestr:
            assert(size == 4)
        elif "h" in self.opcodestr:
            assert(size == 2)
        elif "b" in self.opcodestr:
            assert(size == 1)
        else:
            assert(False)


class CmpRegOp:
    def __init__(self):
        self.ops = {
            "cmp": MicrOp.OP_CMP,
        }
        self.opcodestr = random.choice(list(self.ops.keys()))
        self.opcode = self.ops[self.opcodestr]
        self.r1 = Register(random.randrange(32))
        self.r2 = Register(random.randrange(32))
        self.cr = Register(random.randrange(8))

    def generate_instruction(self):
        string = "{} {}, 0, {}, {}\n".format(self.opcodestr,
                                             self.cr.num,
                                             self.r1.num,
                                             self.r2.num)
        return string

    def check_results(self, pdecode2):
        r1sel = yield pdecode2.e.read_reg1.data
        r2sel = yield pdecode2.e.read_reg2.data
        crsel = yield pdecode2.dec.BF

        assert(r1sel == self.r1.num)
        assert(r2sel == self.r2.num)
        assert(crsel == self.cr.num)


class RotateOp:
    def __init__(self):
        self.ops = {
            "rlwinm": MicrOp.OP_CMP,
            "rlwnm": MicrOp.OP_CMP,
            "rlwimi": MicrOp.OP_CMP,
            "rlwinm.": MicrOp.OP_CMP,
            "rlwnm.": MicrOp.OP_CMP,
            "rlwimi.": MicrOp.OP_CMP,
        }
        self.opcodestr = random.choice(list(self.ops.keys()))
        self.opcode = self.ops[self.opcodestr]
        self.r1 = Register(random.randrange(32))
        self.r2 = Register(random.randrange(32))
        self.shift = random.randrange(32)
        self.mb = random.randrange(32)
        self.me = random.randrange(32)

    def generate_instruction(self):
        string = "{} {},{},{},{},{}\n".format(self.opcodestr,
                                              self.r1.num,
                                              self.r2.num,
                                              self.shift,
                                              self.mb,
                                              self.me)
        return string

    def check_results(self, pdecode2):
        r1sel = yield pdecode2.e.write_reg.data
        r2sel = yield pdecode2.e.read_reg3.data
        dec = pdecode2.dec

        if "i" in self.opcodestr:
            shift = yield dec.SH
        else:
            shift = yield pdecode2.e.read_reg2.data
        mb = yield dec.MB
        me = yield dec.ME

        assert(r1sel == self.r1.num)
        assert(r2sel == self.r2.num)
        assert(shift == self.shift)
        assert(mb == self.mb)
        assert(me == self.me)

        rc = yield pdecode2.e.rc.data
        if '.' in self.opcodestr:
            assert(rc == 1)
        else:
            assert(rc == 0)


class Branch:
    def __init__(self):
        self.ops = {
            "b": MicrOp.OP_B,
            "bl": MicrOp.OP_B,
            "ba": MicrOp.OP_B,
            "bla": MicrOp.OP_B,
        }
        self.opcodestr = random.choice(list(self.ops.keys()))
        self.opcode = self.ops[self.opcodestr]
        self.addr = random.randrange(2**23) * 4

    def generate_instruction(self):
        string = "{} {}\n".format(self.opcodestr,
                                  self.addr)
        return string

    def check_results(self, pdecode2):
        imm = yield pdecode2.e.imm_data.data

        assert(imm == self.addr)
        lk = yield pdecode2.e.lk
        if "l" in self.opcodestr:
            assert(lk == 1)
        else:
            assert(lk == 0)
        aa = yield pdecode2.dec.AA
        if "a" in self.opcodestr:
            assert(aa == 1)
        else:
            assert(aa == 0)


class BranchCond:
    def __init__(self):
        self.ops = {
            "bc": MicrOp.OP_B,
            "bcl": MicrOp.OP_B,
            "bca": MicrOp.OP_B,
            "bcla": MicrOp.OP_B,
        }
        # Given in Figure 40 "BO field encodings" in section 2.4, page
        # 33 of the Power ISA v3.0B manual
        self.branchops = [0b00000, 0b00010, 0b00100, 0b01000, 0b01010,
                          0b01100, 0b10000, 0b10100]
        self.opcodestr = random.choice(list(self.ops.keys()))
        self.opcode = self.ops[self.opcodestr]
        self.addr = random.randrange(2**13) * 4
        self.bo = random.choice(self.branchops)
        self.bi = random.randrange(32)

    def generate_instruction(self):
        string = "{} {},{},{}\n".format(self.opcodestr,
                                        self.bo,
                                        self.bi,
                                        self.addr)
        return string

    def check_results(self, pdecode2):
        imm = yield pdecode2.e.imm_data.data
        bo = yield pdecode2.dec.BO
        bi = yield pdecode2.dec.BI

        assert(imm == self.addr)
        assert(bo == self.bo)
        assert(bi == self.bi)
        lk = yield pdecode2.e.lk
        if "l" in self.opcodestr:
            assert(lk == 1)
        else:
            assert(lk == 0)
        aa = yield pdecode2.dec.AA
        if "a" in self.opcodestr:
            assert(aa == 1)
        else:
            assert(aa == 0)

        cr_sel = yield pdecode2.e.read_cr1.data
        assert cr_sel == (self.bi//8), f"{cr_sel} {self.bi}"



class BranchRel:
    def __init__(self):
        self.ops = {
            "bclr": MicrOp.OP_B,
            "bcctr": MicrOp.OP_B,
            "bclrl": MicrOp.OP_B,
            "bcctrl": MicrOp.OP_B,
        }
        # Given in Figure 40 "BO field encodings" in section 2.4, page
        # 33 of the Power ISA v3.0B manual
        self.branchops = [0b00100, 0b01100, 0b10100]
        self.opcodestr = random.choice(list(self.ops.keys()))
        self.opcode = self.ops[self.opcodestr]
        self.bh = random.randrange(4)
        self.bo = random.choice(self.branchops)
        self.bi = random.randrange(32)

    def generate_instruction(self):
        string = "{} {},{},{}\n".format(self.opcodestr,
                                        self.bo,
                                        self.bi,
                                        self.bh)
        return string

    def check_results(self, pdecode2):
        bo = yield pdecode2.dec.BO
        bi = yield pdecode2.dec.BI

        assert(bo == self.bo)
        assert(bi == self.bi)

        spr = yield pdecode2.e.read_spr2.data
        if "lr" in self.opcodestr:
            assert(spr == SPR.LR.value)
        else:
            assert(spr == SPR.CTR.value)

        lk = yield pdecode2.e.lk
        if self.opcodestr[-1] == 'l':
            assert(lk == 1)
        else:
            assert(lk == 0)

class CROp:
    def __init__(self):
        self.ops = {
            "crand": MicrOp.OP_CROP,
        }
        # Given in Figure 40 "BO field encodings" in section 2.4, page
        # 33 of the Power ISA v3.0B manual
        self.opcodestr = random.choice(list(self.ops.keys()))
        self.opcode = self.ops[self.opcodestr]
        self.ba = random.randrange(32)
        self.bb = random.randrange(32)
        self.bt = random.randrange(32)

    def generate_instruction(self):
        string = "{} {},{},{}\n".format(self.opcodestr,
                                        self.bt,
                                        self.ba,
                                        self.bb)
        return string

    def check_results(self, pdecode2):
        cr1 = yield pdecode2.e.read_cr1.data
        assert cr1 == self.ba//4

        cr2 = yield pdecode2.e.read_cr2.data
        assert cr2 == self.bb//4

        cr_out = yield pdecode2.e.write_cr.data
        cr3 = yield pdecode2.e.read_cr3.data
        assert cr_out == self.bt//4
        assert cr3 == self.bt//4



class DecoderTestCase(FHDLTestCase):

    def run_tst(self, kls, name):
        m = Module()
        comb = m.d.comb
        instruction = Signal(32)

        pdecode = create_pdecode()

        m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)
        comb += pdecode2.dec.raw_opcode_in.eq(instruction)
        sim = Simulator(m)

        def process():
            for i in range(20):
                checker = kls()
                ins = checker.generate_instruction()
                print("instr", ins.strip())
                for mode in [0, 1]:

                    # turn the instruction into binary data (endian'd)
                    ibin = get_assembled_instruction(ins, mode)
                    print("code", mode, hex(ibin), bin(ibin))

                    # ask the decoder to decode this binary data (endian'd)
                    yield pdecode2.dec.bigendian.eq(mode)  # little / big?
                    yield instruction.eq(ibin)            # raw binary instr.
                    yield Delay(1e-6)

                    yield from checker.check_results(pdecode2)

        sim.add_process(process)
        ports = pdecode2.ports()
        print(ports)
        with sim.write_vcd("%s.vcd" % name, "%s.gtkw" % name,
                           traces=ports):
            sim.run()

    def test_reg_reg(self):
        self.run_tst(RegRegOp, "reg_reg")

    def test_reg_imm(self):
        self.run_tst(RegImmOp, "reg_imm")

    def test_ldst_imm(self):
        self.run_tst(LdStOp, "ldst_imm")

    def test_cmp_reg(self):
        self.run_tst(CmpRegOp, "cmp_reg")

    def test_rot(self):
        self.run_tst(RotateOp, "rot")

    def test_branch(self):
        self.run_tst(Branch, "branch")

    def test_branch_cond(self):
        self.run_tst(BranchCond, "branch_cond")

    def test_branch_rel(self):
        self.run_tst(BranchRel, "branch_rel")

    def test_cr_op(self):
        self.run_tst(CROp, "cr_op")


if __name__ == "__main__":
    unittest.main()
