# This stage is intended to do most of the work of executing the ALU
# instructions. This would be like the additions, logical operations,
# and shifting, as well as carry and overflow generation. This module
# however should not gate the carry or overflow, that's up to the
# output stage
from nmigen import (Module, Signal, Cat, Repl, Mux, Const)
from nmutil.pipemodbase import PipeModBase
from soc.alu.pipe_data import ALUOutputData
from soc.shift_rot.pipe_data import ShiftRotInputData
from ieee754.part.partsig import PartitionedSignal
from soc.decoder.power_enums import InternalOp
from soc.shift_rot.rotator import Rotator

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
        return ALUOutputData(self.pspec) # TODO: ALUIntermediateData

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        m.submodules.rotator = rotator = Rotator()
        comb += [
            rotator.rs.eq(self.i.rs),
            rotator.ra.eq(self.i.ra),
            rotator.shift.eq(self.i.rb),
            rotator.insn.eq(self.i.ctx.op.insn),
            rotator.is_32bit.eq(self.i.ctx.op.is_32bit),
            rotator.arith.eq(self.i.ctx.op.is_signed),
        ]

        # Defaults
        comb += [rotator.right_shift.eq(0),
                 rotator.clear_left.eq(0),
                 rotator.clear_right.eq(0)]

        comb += [self.o.o.eq(rotator.result_o),
                 self.o.carry_out.eq(rotator.carry_out_o)]

        with m.Switch(self.i.ctx.op.insn_type):
            with m.Case(InternalOp.OP_SHL):
                comb += [rotator.right_shift.eq(0),
                        rotator.clear_left.eq(0),
                        rotator.clear_right.eq(0)]
            with m.Case(InternalOp.OP_SHR):
                comb += [rotator.right_shift.eq(1),
                        rotator.clear_left.eq(0),
                        rotator.clear_right.eq(0)]
                





        ###### sticky overflow and context, both pass-through #####

        comb += self.o.so.eq(self.i.so)
        comb += self.o.ctx.eq(self.i.ctx)

        return m
