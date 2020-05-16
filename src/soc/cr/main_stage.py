# This stage is intended to do Condition Register instructions
# and output, as well as carry and overflow generation.
# NOTE: we really should be doing the field decoding which
# selects which bits of CR are to be read / written, back in the
# decoder / insn-isue, have both self.i.cr and self.o.cr
# be broken down into 4-bit-wide "registers", with their
# own "Register File" (indexed by bt, ba and bb),
# exactly how INT regs are done (by RA, RB, RS and RT)
# however we are pushed for time so do it as *one* register.

from nmigen import (Module, Signal, Cat, Repl, Mux, Const, Array)
from nmutil.pipemodbase import PipeModBase
from soc.cr.pipe_data import CRInputData, CROutputData
from soc.decoder.power_enums import InternalOp

from soc.decoder.power_fields import DecodeFields
from soc.decoder.power_fieldsn import SignalBitRange


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

        # default: cr_o remains same as cr input unless modified, below
        cr_o = Signal.like(self.i.cr)
        comb += cr_o.eq(self.i.cr)

        ##### prepare inputs / temp #####

        # Generate array for cr input so bits can be selected
        cr_arr = Array([Signal(name=f"cr_arr_{i}") for i in range(32)])
        for i in range(32):
            comb += cr_arr[i].eq(self.i.cr[31-i])

        # Generate array for cr output so the bit to write to can be
        # selected by a signal
        cr_out_arr = Array([Signal(name=f"cr_out_{i}") for i in range(32)])
        for i in range(32):
            comb += cr_o[31-i].eq(cr_out_arr[i])
            comb += cr_out_arr[i].eq(cr_arr[i])

        # Ugh. mtocrf and mtcrf have one random bit differentiating
        # them. This bit is not in any particular field, so this
        # extracts that bit from the instruction
        move_one = Signal(reset_less=True)
        comb += move_one.eq(self.i.ctx.op.insn[20])

        # crand/cror and friends get decoded to the same opcode, but
        # one of the fields inside the instruction is a 4 bit lookup
        # table. This lookup table gets indexed by bits a and b from
        # the CR to determine what the resulting bit should be.

        # Grab the lookup table for cr_op type instructions
        lut = Signal(4, reset_less=True)
        # There's no field, just have to grab it directly from the insn
        comb += lut.eq(self.i.ctx.op.insn[6:10])

        # Generate the mask for mtcrf, mtocrf, and mfocrf
        fxm = Signal(xfx_fields['FXM'][0:-1].shape())
        comb += fxm.eq(xfx_fields['FXM'][0:-1])

        # replicate every fxm field in the insn to 4-bit, as a mask
        mask = Signal(32, reset_less=True)
        for i in range(8):
            comb += mask[i*4:(i+1)*4].eq(Repl(fxm[i], 4))

        #################################
        ##### main switch statement #####

        with m.Switch(op.insn_type):
            ##### mcrf #####
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

            ##### crand, cror, crnor etc. #####
            with m.Case(InternalOp.OP_CROP):
                # Get the bit selector fields from the instruction
                bt = Signal(xl_fields['BT'][0:-1].shape())
                ba = Signal(xl_fields['BA'][0:-1].shape())
                bb = Signal(xl_fields['BB'][0:-1].shape())
                comb += bt.eq(xl_fields['BT'][0:-1])
                comb += ba.eq(xl_fields['BA'][0:-1])
                comb += bb.eq(xl_fields['BB'][0:-1])

                # Extract the two input bits from the CR
                bit_a = Signal(reset_less=True)
                bit_b = Signal(reset_less=True)
                comb += bit_a.eq(cr_arr[ba])
                comb += bit_b.eq(cr_arr[bb])

                # Use the two input bits to look up the result in the
                # lookup table
                bit_out = Signal(reset_less=True)
                comb += bit_out.eq(Mux(bit_b,
                                       Mux(bit_a, lut[3], lut[1]),
                                       Mux(bit_a, lut[2], lut[0])))
                # Set the output to the result above
                comb += cr_out_arr[bt].eq(bit_out)

            ##### mtcrf #####
            with m.Case(InternalOp.OP_MTCRF):
                # mtocrf and mtcrf are essentially identical
                # put input (RA) - mask-selected - into output CR, leave
                # rest of CR alone.
                comb += cr_o.eq((self.i.a[0:32] & mask) |
                                     (self.i.cr & ~mask))

            with m.Case(InternalOp.OP_MFCR):
                # mfocrf
                with m.If(move_one):
                    comb += self.o.o.eq(self.i.cr & mask)
                # mfcrf
                with m.Else():
                    comb += self.o.o.eq(self.i.cr)

        # output and context
        comb += self.o.cr.eq(cr_o)
        comb += self.o.ctx.eq(self.i.ctx)

        return m
