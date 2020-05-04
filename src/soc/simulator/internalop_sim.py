from soc.decoder.power_enums import (Function, Form, InternalOp,
                                     In1Sel, In2Sel, In3Sel, OutSel,
                                     RC, LdstLen, CryIn, get_csv,
                                     single_bit_flags,
                                     get_signal_name, default_values)
import math


class MemorySim:
    def __init__(self, bytes_per_word=8):
        self.mem = {}
        self.bytes_per_word = bytes_per_word
        self.word_log2 = math.ceil(math.log2(bytes_per_word))

    def _get_shifter_mask(self, width, remainder):
        shifter = ((self.bytes_per_word - width) - remainder) * \
            8  # bits per byte
        mask = (1 << (width * 8)) - 1
        return shifter, mask

    # TODO: Implement ld/st of lesser width
    def ld(self, address, width=8):
        remainder = address & (self.bytes_per_word - 1)
        address = address >> self.word_log2
        assert remainder & (width - 1) == 0, "Unaligned access unsupported!"
        if address in self.mem:
            val = self.mem[address]
        else:
            val = 0

        if width != self.bytes_per_word:
            shifter, mask = self._get_shifter_mask(width, remainder)
            val = val & (mask << shifter)
            val >>= shifter
        print("Read {:x} from addr {:x}".format(val, address))
        return val

    def st(self, address, value, width=8):
        remainder = address & (self.bytes_per_word - 1)
        address = address >> self.word_log2
        assert remainder & (width - 1) == 0, "Unaligned access unsupported!"
        print("Writing {:x} to addr {:x}".format(value, address))
        if width != self.bytes_per_word:
            if address in self.mem:
                val = self.mem[address]
            else:
                val = 0
            shifter, mask = self._get_shifter_mask(width, remainder)
            val &= ~(mask << shifter)
            val |= value << shifter
            self.mem[address] = val
        else:
            self.mem[address] = value


class RegFile:
    def __init__(self):
        self.regfile = [0] * 32
        self.sprs = {}

    def write_reg(self, regnum, value):
        all1s = (1 << 64)-1  # 64 bits worth of 1s
        value &= all1s
        print("Writing {:x} to reg r{}".format(value, regnum))
        self.regfile[regnum] = value

    def read_reg(self, regnum):
        val = self.regfile[regnum]
        print("Read {:x} from reg r{}".format(val, regnum))
        return val

    def assert_gpr(self, gpr, val):
        reg_val = self.read_reg(gpr)
        msg = "reg r{} got {:x}, expecting {:x}".format(
            gpr, reg_val, val)
        assert reg_val == val, msg

    def assert_gprs(self, gprs):
        for k, v in list(gprs.items()):
            self.assert_gpr(k, v)

    def set_xer(self, result, operanda, operandb):
        xer = 0
        if result & 1 << 64:
            xer |= XER.CA

        self.xer = xer


class InternalOpSimulator:
    def __init__(self):
        self.mem_sim = MemorySim()
        self.regfile = RegFile()

    def execute_alu_op(self, op1, op2, internal_op, carry=0):
        print(internal_op)
        if internal_op == InternalOp.OP_ADD.value:
            return op1 + op2 + carry
        elif internal_op == InternalOp.OP_AND.value:
            return op1 & op2
        elif internal_op == InternalOp.OP_OR.value:
            return op1 | op2
        elif internal_op == InternalOp.OP_MUL_L64.value:
            return op1 * op2
        else:
            assert False, "Not implemented"

    def update_cr0(self, result):
        if result == 0:
            self.cr0 = 0b001
        elif result >> 63:
            self.cr0 = 0b100
        else:
            self.cr0 = 0b010
        print("update_cr0", self.cr0)

    def alu_op(self, pdecode2):
        all1s = (1 << 64)-1  # 64 bits worth of 1s
        internal_op = yield pdecode2.dec.op.internal_op
        operand1 = 0
        operand2 = 0
        result = 0
        carry = 0
        r1_ok = yield pdecode2.e.read_reg1.ok
        r2_ok = yield pdecode2.e.read_reg2.ok
        r3_ok = yield pdecode2.e.read_reg3.ok
        imm_ok = yield pdecode2.e.imm_data.ok
        if r1_ok:
            r1_sel = yield pdecode2.e.read_reg1.data
            operand1 = self.regfile.read_reg(r1_sel)
        elif r3_ok:
            r3_sel = yield pdecode2.e.read_reg3.data
            operand1 = self.regfile.read_reg(r3_sel)
        if r2_ok:
            r2_sel = yield pdecode2.e.read_reg2.data
            operand2 = self.regfile.read_reg(r2_sel)
        if imm_ok:
            operand2 = yield pdecode2.e.imm_data.data

        inv_a = yield pdecode2.dec.op.inv_a
        if inv_a:
            operand1 = (~operand1) & all1s

        cry_in = yield pdecode2.dec.op.cry_in
        if cry_in == CryIn.ONE.value:
            carry = 1
        elif cry_in == CryIn.CA.value:
            carry = self.carry_out

        # TODO rc_sel = yield pdecode2.dec.op.rc_sel
        result = self.execute_alu_op(operand1, operand2, internal_op,
                                     carry=carry)

        cry_out = yield pdecode2.dec.op.cry_out
        rc = yield pdecode2.e.rc.data

        if rc:
            self.update_cr0(result)
        if cry_out == 1:
            self.carry_out = (result >> 64)
            print("setting carry_out", self.carry_out)

        ro_ok = yield pdecode2.e.write_reg.ok
        if ro_ok:
            ro_sel = yield pdecode2.e.write_reg.data
            self.regfile.write_reg(ro_sel, result)

    def mem_op(self, pdecode2):
        internal_op = yield pdecode2.dec.op.internal_op
        addr_reg = yield pdecode2.e.read_reg1.data
        addr = self.regfile.read_reg(addr_reg)

        imm_ok = yield pdecode2.e.imm_data.ok
        r2_ok = yield pdecode2.e.read_reg2.ok
        width = yield pdecode2.e.data_len
        if imm_ok:
            imm = yield pdecode2.e.imm_data.data
            addr += imm
        elif r2_ok:
            r2_sel = yield pdecode2.e.read_reg2.data
            addr += self.regfile.read_reg(r2_sel)
        if internal_op == InternalOp.OP_STORE.value:
            val_reg = yield pdecode2.e.read_reg3.data
            val = self.regfile.read_reg(val_reg)
            self.mem_sim.st(addr, val, width)
        elif internal_op == InternalOp.OP_LOAD.value:
            dest_reg = yield pdecode2.e.write_reg.data
            val = self.mem_sim.ld(addr, width)
            self.regfile.write_reg(dest_reg, val)

    def execute_op(self, pdecode2):
        function = yield pdecode2.dec.op.function_unit
        if function == Function.ALU.value:
            yield from self.alu_op(pdecode2)
        elif function == Function.LDST.value:
            yield from self.mem_op(pdecode2)
