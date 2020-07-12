# This stage is intended to do most of the work of executing shift
# instructions, as well as carry and overflow generation. This module
# however should not gate the carry or overflow, that's up to the
# output stage
from nmigen import (Module, Signal, Cat, Repl, Mux, Const)
from nmutil.pipemodbase import PipeModBase
from soc.fu.logical.pipe_data import LogicalOutputData
from soc.fu.shift_rot.pipe_data import ShiftRotInputData
from ieee754.part.partsig import PartitionedSignal
from soc.decoder.power_enums import MicrOp
from soc.fu.shift_rot.rotator import Rotator

from soc.decoder.power_fields import DecodeFields
from soc.decoder.power_fieldsn import SignalBitRange


class ShiftRotMainStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "main")
        self.fields = DecodeFields(SignalBitRange, [self.i.ctx.op.insn])
        self.fields.create_specs()

    def ispec(self):
        return ShiftRotInputData(self.pspec)

    def ospec(self):
        return LogicalOutputData(self.pspec)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        op = self.i.ctx.op
        o = self.o.o

        # obtain me and mb fields from instruction.
        m_fields = self.fields.instrs['M']
        md_fields = self.fields.instrs['MD']
        mb = Signal(m_fields['MB'][0:-1].shape())
        me = Signal(m_fields['ME'][0:-1].shape())
        mb_extra = Signal(1, reset_less=True)
        comb += mb.eq(m_fields['MB'][0:-1])
        comb += me.eq(m_fields['ME'][0:-1])
        comb += mb_extra.eq(md_fields['mb'][0:-1][0])

        # set up microwatt rotator module
        m.submodules.rotator = rotator = Rotator()
        comb += [
            rotator.me.eq(me),
            rotator.mb.eq(mb),
            rotator.mb_extra.eq(mb_extra),
            rotator.rs.eq(self.i.rs),
            rotator.ra.eq(self.i.a),
            rotator.shift.eq(self.i.rb),
            rotator.is_32bit.eq(op.is_32bit),
            rotator.arith.eq(op.is_signed),
            # rot_sign_ext <= '1' when e_in.insn_type = OP_EXTSWSLI else '0';
            rotator.sign_ext_rs.eq(0), # XXX TODO
        ]

        comb += o.ok.eq(1) # defaults to enabled

        # instruction rotate type
        mode = Signal(3, reset_less=True)
        with m.Switch(op.insn_type):
            with m.Case(MicrOp.OP_SHL):  comb += mode.eq(0b000)
            with m.Case(MicrOp.OP_SHR):  comb += mode.eq(0b001) # R-shift
            with m.Case(MicrOp.OP_RLC):  comb += mode.eq(0b110) # clear LR
            with m.Case(MicrOp.OP_RLCL): comb += mode.eq(0b010) # clear L
            with m.Case(MicrOp.OP_RLCR): comb += mode.eq(0b100) # clear R
            with m.Default():
                comb += o.ok.eq(0) # otherwise disable

        comb += Cat(rotator.right_shift,
                    rotator.clear_left,
                    rotator.clear_right).eq(mode)

        # outputs from the microwatt rotator module
        comb += [o.data.eq(rotator.result_o),
                 self.o.xer_ca.data.eq(Repl(rotator.carry_out_o, 2))]

        ###### sticky overflow and context, both pass-through #####

        comb += self.o.ctx.eq(self.i.ctx)

        return m
