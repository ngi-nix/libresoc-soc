# This stage is intended to do most of the work of executing Logical
# instructions. This is OR, AND, XOR, POPCNT, PRTY, CMPB, BPERMD, CNTLZ
# however input and output stages also perform bit-negation on input(s)
# and output, as well as carry and overflow generation.
# This module however should not gate the carry or overflow, that's up
# to the output stage

from nmigen import (Module, Signal, Cat, Repl, Mux, Const, Array)
from nmutil.pipemodbase import PipeModBase
from soc.cr.pipe_data import CRInputData, CROutputData
from soc.decoder.power_enums import InternalOp

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
        return CROutputData(self.pspec)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        op = self.i.ctx.op
        xl_fields = self.fields.instrs['XL']
        xfx_fields = self.fields.instrs['XFX']

        cr_output = Signal.like(self.i.cr)
        comb += cr_output.eq(self.i.cr)

        # Generate array for cr input so bits can be selected
        cr_arr = Array([Signal(name=f"cr_arr_{i}") for i in range(32)])
        for i in range(32):
            comb += cr_arr[i].eq(self.i.cr[31-i])

        # Generate array for cr output so the bit to write to can be
        # selected by a signal
        cr_out_arr = Array([Signal(name=f"cr_out_{i}") for i in range(32)])
        for i in range(32):
            comb += cr_output[31-i].eq(cr_out_arr[i])
            comb += cr_out_arr[i].eq(cr_arr[i])

        # crand/cror and friends get decoded to the same opcode, but
        # one of the fields inside the instruction is a 4 bit lookup
        # table. This lookup table gets indexed by bits a and b from
        # the CR to determine what the resulting bit should be.

        # Grab the lookup table for cr_op type instructions
        lut = Signal(4, reset_less=True)
        # There's no field, just have to grab it directly from the insn
        comb += lut.eq(self.i.ctx.op.insn[6:10])


        # Ugh. mtocrf and mtcrf have one random bit differentiating
        # them. This bit is not in any particular field, so this
        # extracts that bit from the instruction
        move_one = Signal(reset_less=True)
        comb += move_one.eq(self.i.ctx.op.insn[20])

        with m.Switch(op.insn_type):
            with m.Case(InternalOp.OP_MCRF):
                # MCRF copies the 4 bits of crA to crB (for instance
                # copying cr2 to cr1)

                # The destination CR
                bf = Signal(xl_fields['BF'][0:-1].shape())
                comb += bf.eq(xl_fields['BF'][0:-1])
                # the source CR
                bfa = Signal(xl_fields['BFA'][0:-1].shape())
                comb += bfa.eq(xl_fields['BFA'][0:-1])

                for i in range(4):
                    comb += cr_out_arr[bf*4 + i].eq(cr_arr[bfa*4 + i])
            with m.Case(InternalOp.OP_CROP):
                # Get the bit selector fields from the instruction
                bt = Signal(xl_fields['BT'][0:-1].shape())
                comb += bt.eq(xl_fields['BT'][0:-1])
                ba = Signal(xl_fields['BA'][0:-1].shape())
                comb += ba.eq(xl_fields['BA'][0:-1])
                bb = Signal(xl_fields['BB'][0:-1].shape())
                comb += bb.eq(xl_fields['BB'][0:-1])

                # Extract the two input bits from the CR
                bit_a = Signal(reset_less=True)
                bit_b = Signal(reset_less=True)
                comb += bit_a.eq(cr_arr[ba])
                comb += bit_b.eq(cr_arr[bb])

                bit_out = Signal(reset_less=True)

                # Use the two input bits to look up the result in the
                # lookup table
                comb += bit_out.eq(Mux(bit_b,
                                       Mux(bit_a, lut[3], lut[1]),
                                       Mux(bit_a, lut[2], lut[0])))
                # Set the output to the result above
                comb += cr_out_arr[bt].eq(bit_out)

            with m.Case(InternalOp.OP_MTCRF):
                fxm = Signal(xfx_fields['FXM'][0:-1].shape())
                comb += fxm.eq(xfx_fields['FXM'][0:-1])

                # mtcrf
                mask = Signal(32, reset_less=True)

                for i in range(8):
                    comb += mask[i*4:(i+1)*4].eq(Repl(fxm[i], 4))

                comb += cr_output.eq((self.i.a[0:32] & mask) |
                                     (self.i.cr & ~mask))
                    

        comb += self.o.cr.eq(cr_output)
        comb += self.o.ctx.eq(self.i.ctx)

        return m
