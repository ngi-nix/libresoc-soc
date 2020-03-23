from soc.decoder.power_enums import (Function, Form, InternalOp,
                         In1Sel, In2Sel, In3Sel, OutSel, RC, LdstLen,
                         CryIn, get_csv, single_bit_flags,
                         get_signal_name, default_values)


class MemorySim:
    def __init__(self):
        self.mem = {}


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
            return 0

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

    def execute_op(self, pdecode2):
        function = yield pdecode2.dec.op.function_unit
        if function == Function.ALU.value:
            yield from self.alu_op(pdecode2)
