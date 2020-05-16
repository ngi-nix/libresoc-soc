# This stage is intended to do most of the work of executing Logical
# instructions. This is OR, AND, XOR, POPCNT, PRTY, CMPB, BPERMD, CNTLZ
# however input and output stages also perform bit-negation on input(s)
# and output, as well as carry and overflow generation.
# This module however should not gate the carry or overflow, that's up
# to the output stage

from nmigen import (Module, Signal, Cat, Repl, Mux, Const, Array)
from nmutil.pipemodbase import PipeModBase
from soc.cr.pipe_data import CRInputData, CROutputData
from ieee754.part.partsig import PartitionedSignal
from soc.decoder.power_enums import InternalOp
from soc.countzero.countzero import ZeroCounter

from soc.decoder.power_fields import DecodeFields
from soc.decoder.power_fieldsn import SignalBitRange


def array_of(count, bitwidth):
    res = []
    for i in range(count):
        res.append(Signal(bitwidth, reset_less=True))
    return res


class CRMainStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "main")
        self.fields = DecodeFields(SignalBitRange, [self.i.ctx.op.insn])
        self.fields.create_specs()

    def ispec(self):
        return CRInputData(self.pspec)

    def ospec(self):
        return CROutputData(self.pspec) # TODO: ALUIntermediateData

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        op = self.i.ctx.op
        xl_fields = self.fields.instrs['XL']

        cr_output = Signal.like(self.i.cr)
        comb += cr_output.eq(self.i.cr)

        # Generate array for cr input so bits can be selected
        cr_arr = Array([Signal() for _ in range(32)])
        for i in range(32):
            comb += cr_arr[i].eq(self.i.cr[31-i])

        # Generate array for cr output so the bit to write to can be
        # selected by a signal
        cr_out_arr = Array([Signal() for _ in range(32)])
        for i in range(32):
            comb += cr_output[31-i].eq(cr_out_arr[i])
            comb += cr_out_arr[i].eq(cr_arr[i])
            

        with m.Switch(op.insn_type):
            with m.Case(InternalOp.OP_MCRF):
                bf = Signal(xl_fields['BF'][0:-1].shape())
                comb += bf.eq(xl_fields['BF'][0:-1])
                bfa = Signal(xl_fields['BFA'][0:-1].shape())
                comb += bfa.eq(xl_fields['BFA'][0:-1])

                for i in range(4):
                    comb += cr_out_arr[bf*4 + i].eq(cr_arr[bfa*4 + i])

                
        comb += self.o.cr.eq(cr_output)
        comb += self.o.ctx.eq(self.i.ctx)

        return m
