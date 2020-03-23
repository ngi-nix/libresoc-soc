from soc.decoder.power_enums import (Function, Form, InternalOp,
                         In1Sel, In2Sel, In3Sel, OutSel, RC, LdstLen,
                         CryIn, get_csv, single_bit_flags,
                         get_signal_name, default_values)
import math


class MemorySim:
    def __init__(self, bytes_per_word=8):
        self.mem = {}
        self.bytes_per_word = bytes_per_word
        self.word_log2 = math.ceil(math.log2(bytes_per_word))

    # TODO: Implement ld/st of lesser width
    def ld(self, address):
        address = address >> self.word_log2
        if address in self.mem:
            val = self.mem[address]
        else:
            val = 0
        print("Read {:x} from addr {:x}".format(val, address))
        return val

    def st(self, address, value):
        address = address >> self.word_log2
        print("Writing {:x} to addr {:x}".format(value, address))
        self.mem[address] = value


class RegFile:
    def __init__(self):
        self.regfile = [0] * 32
        self.sprs = {}

    def write_reg(self, regnum, value):
        print("Writing {:x} to reg r{}".format(value, regnum))
        self.regfile[regnum] = value

    def read_reg(self, regnum):
        val = self.regfile[regnum]
        print("Read {:x} from reg r{}".format(val, regnum))
        return val

    def assert_gprs(self, gprs):
        for k,v in list(gprs.items()):
            reg_val = self.read_reg(k)
            msg = "reg r{} got {:x}, expecting {:x}".format(
                k, reg_val, v)
            assert reg_val == v, msg


class InternalOpSimulator:
    def __init__(self):
        self.mem_sim = MemorySim()
        self.regfile = RegFile()

    def execute_alu_op(self, op1, op2, internal_op):
        print(internal_op)
        if internal_op == InternalOp.OP_ADD.value:
            return op1 + op2
        elif internal_op == InternalOp.OP_AND.value:
            return op1 & op2
        else:
            assert(False, "Not implemented")

    def alu_op(self, pdecode2):
        internal_op = yield pdecode2.dec.op.internal_op
        operand1 = 0
        operand2 = 0
        result = 0
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

        result = self.execute_alu_op(operand1, operand2, internal_op)
        ro_ok = yield pdecode2.e.write_reg.ok
        if ro_ok:
            ro_sel = yield pdecode2.e.write_reg.data
            self.regfile.write_reg(ro_sel, result)

    def mem_op(self, pdecode2):
        internal_op = yield pdecode2.dec.op.internal_op
        addr_reg = yield pdecode2.e.read_reg1.data
        addr = self.regfile.read_reg(addr_reg)
        
        imm_ok = yield pdecode2.e.imm_data.ok
        if imm_ok:
            imm = yield pdecode2.e.imm_data.data
            addr += imm
        if internal_op == InternalOp.OP_STORE.value:
            val_reg = yield pdecode2.e.read_reg3.data
            val = self.regfile.read_reg(val_reg)
            self.mem_sim.st(addr, val)
        elif internal_op == InternalOp.OP_LOAD.value:
            dest_reg = yield pdecode2.e.write_reg.data
            val = self.mem_sim.ld(addr)
            self.regfile.write_reg(dest_reg, val)


    def execute_op(self, pdecode2):
        function = yield pdecode2.dec.op.function_unit
        if function == Function.ALU.value:
            yield from self.alu_op(pdecode2)
        elif function == Function.LDST.value:
            yield from self.mem_op(pdecode2)
