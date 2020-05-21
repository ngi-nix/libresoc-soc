# This stage is intended to do Condition Register instructions
# and output, as well as carry and overflow generation.
# NOTE: with the exception of mtcrf and mfcr, we really should be doing
# the field decoding which
# selects which bits of CR are to be read / written, back in the
# decoder / insn-isue, have both self.i.cr and self.o.cr
# be broken down into 4-bit-wide "registers", with their
# own "Register File" (indexed by bt, ba and bb),
# exactly how INT regs are done (by RA, RB, RS and RT)
# however we are pushed for time so do it as *one* register.

from nmigen import (Module, Signal, Cat, Repl, Mux, Const, Array)
from nmutil.pipemodbase import PipeModBase
from soc.fu.cr.pipe_data import CRInputData, CROutputData
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
        a, full_cr = self.i.a, self.i.full_cr
        cr_a, cr_b, cr_c = self.i.cr_a, self.i.cr_b, self.i.cr_c
        xl_fields = self.fields.FormXL
        xfx_fields = self.fields.FormXFX

        cr_o = self.o.cr_o

        # Generate the mask for mtcrf, mtocrf, and mfocrf
        # replicate every fxm field in the insn to 4-bit, as a mask
        FXM = xfx_fields.FXM[0:-1]
        mask = Signal(32, reset_less=True)
        comb += mask.eq(Cat(*[Repl(FXM[i], 4) for i in range(8)]))

        # Generate array of bits for cr_a and cr_b
        cr_a_arr = Array([cr_a[i] for i in range(4)])
        cr_b_arr = Array([cr_b[i] for i in range(4)])
        cr_o_arr = Array([cr_o[i] for i in range(4)])

        comb += cr_o.eq(cr_c)

        with m.Switch(op.insn_type):
            ##### mcrf #####
            with m.Case(InternalOp.OP_MCRF):
                # MCRF copies the 4 bits of crA to crB (for instance
                # copying cr2 to cr1)
                # Since it takes in a 4 bit cr, and outputs a 4 bit
                # cr, we don't have to do anything special
                comb += cr_o.eq(cr_a)

            # ##### crand, cror, crnor etc. #####
            with m.Case(InternalOp.OP_CROP):
                # crand/cror and friends get decoded to the same opcode, but
                # one of the fields inside the instruction is a 4 bit lookup
                # table. This lookup table gets indexed by bits a and b from
                # the CR to determine what the resulting bit should be.

                # Grab the lookup table for cr_op type instructions
                lut = Signal(4, reset_less=True)
                # There's no field, just have to grab it directly from the insn
                comb += lut.eq(op.insn[6:10])

                # Get the bit selector fields from the
                # instruction. This operation takes in the little CR
                # bitfields, so these fields need to get truncated to
                # the least significant 2 bits
                BT = xl_fields.BT[0:-1]
                BA = xl_fields.BA[0:-1]
                BB = xl_fields.BB[0:-1]
                bt = Signal(2, reset_less=True)
                ba = Signal(2, reset_less=True)
                bb = Signal(2, reset_less=True)

                # Stupid bit ordering stuff.  Because POWER.
                comb += bt.eq(3-BT[0:2])
                comb += ba.eq(3-BA[0:2])
                comb += bb.eq(3-BB[0:2])

                # Extract the two input bits from the CRs
                bit_a = Signal(reset_less=True)
                bit_b = Signal(reset_less=True)
                comb += bit_a.eq(cr_a_arr[ba])
                comb += bit_b.eq(cr_b_arr[bb])

                # look up the output bit in the lookup table
                bit_o = Signal()
                comb += bit_o.eq(Mux(bit_b,
                                     Mux(bit_a, lut[3], lut[1]),
                                     Mux(bit_a, lut[2], lut[0])))

                # insert the output bit into the 4-bit CR output
                comb += cr_o_arr[bt].eq(bit_o)

            ##### mtcrf #####
            with m.Case(InternalOp.OP_MTCRF):
                # mtocrf and mtcrf are essentially identical
                # put input (RA) - mask-selected - into output CR, leave
                # rest of CR alone.
                comb += self.o.full_cr.eq((a[0:32] & mask) | (full_cr & ~mask))

            # ##### mfcr #####
            with m.Case(InternalOp.OP_MFCR):
                # Ugh. mtocrf and mtcrf have one random bit differentiating
                # them. This bit is not in any particular field, so this
                # extracts that bit from the instruction
                move_one = Signal(reset_less=True)
                comb += move_one.eq(op.insn[20])

                # mfocrf
                with m.If(move_one):
                    # output register RT
                    comb += self.o.o.eq(full_cr & mask)
                # mfcrf
                with m.Else():
                    # output register RT
                    comb += self.o.o.eq(full_cr)

        comb += self.o.ctx.eq(self.i.ctx)

        return m
