"""Decode2ToExecute1Type

based on Anton Blanchard microwatt decode2.vhdl

"""
from nmigen import Signal, Record
from nmutil.iocontrol import RecordObject
from soc.decoder.power_enums import InternalOp, CryIn, Function


class Data(Record):

    def __init__(self, width, name):
        name_ok = "%s_ok" % name
        layout = ((name, width), (name_ok, 1))
        Record.__init__(self, layout)
        self.data = getattr(self, name) # convenience
        self.ok = getattr(self, name_ok) # convenience
        self.data.reset_less = True # grrr
        self.reset_less = True # grrr

    def ports(self):
        return [self.data, self.ok]


class Decode2ToExecute1Type(RecordObject):

    def __init__(self, name=None):

        RecordObject.__init__(self, name=name)

        self.valid = Signal(reset_less=True)
        self.insn_type = Signal(InternalOp, reset_less=True)
        self.fn_unit = Signal(Function, reset_less=True)
        self.nia = Signal(64, reset_less=True)
        self.write_reg = Data(5, name="rego")
        self.write_ea = Data(5, name="ea") # for LD/ST in update mode
        self.read_reg1 = Data(5, name="reg1")
        self.read_reg2 = Data(5, name="reg2")
        self.read_reg3 = Data(5, name="reg3")
        self.imm_data = Data(64, name="imm")
        self.write_spr = Data(10, name="spro")
        self.read_spr1 = Data(10, name="spr1")
        self.read_spr2 = Data(10, name="spr2")

        self.read_fast1 = Data(3, name="fast1")
        self.read_fast2 = Data(3, name="fast2")
        self.write_fast1 = Data(3, name="fasto1")
        self.write_fast2 = Data(3, name="fasto2")

        self.read_cr1 = Data(3, name="cr_in1")
        self.read_cr2 = Data(3, name="cr_in2")
        self.read_cr3 = Data(3, name="cr_in2")
        self.read_cr_whole = Signal(reset_less=True)
        self.write_cr = Data(3, name="cr_out")
        self.write_cr_whole = Signal(reset_less=True)
        self.lk = Signal(reset_less=True)
        self.rc = Data(1, "rc")
        self.oe = Data(1, "oe")
        self.invert_a = Signal(reset_less=True)
        self.zero_a = Signal(reset_less=True)
        self.invert_out = Signal(reset_less=True)
        self.input_carry = Signal(CryIn, reset_less=True)
        self.output_carry = Signal(reset_less=True)
        self.input_cr = Signal(reset_less=True)  # instr. has a CR as input
        self.output_cr = Signal(reset_less=True) # instr. has a CR as output
        self.is_32bit = Signal(reset_less=True)
        self.is_signed = Signal(reset_less=True)
        self.insn = Signal(32, reset_less=True)
        self.data_len = Signal(4, reset_less=True) # bytes
        self.byte_reverse  = Signal(reset_less=True)
        self.sign_extend  = Signal(reset_less=True)# do we need this?
        self.update  = Signal(reset_less=True) # LD/ST is "update" variant
        self.traptype  = Signal(4, reset_less=True) # see trap main_stage.py
        self.trapaddr  = Signal(13, reset_less=True)

