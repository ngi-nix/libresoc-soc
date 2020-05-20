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
        a, cr = self.i.a, self.i.cr
        xl_fields = self.fields.FormXL
        xfx_fields = self.fields.FormXFX
        # default: cr_o remains same as cr input unless modified, below
        cr_o = Signal.like(cr)
        comb += cr_o.eq(cr)

        ##### prepare inputs / temp #####

        # Generate array for cr input so bits can be selected
        cr_arr = Array([Signal(name=f"cr_arr_{i}") for i in range(32)])
        for i in range(32):
            comb += cr_arr[i].eq(cr[31-i])

        # Generate array for cr output so the bit to write to can be
        # selected by a signal
        cr_out_arr = Array([Signal(name=f"cr_out_{i}") for i in range(32)])
        for i in range(32):
            comb += cr_o[31-i].eq(cr_out_arr[i])
            comb += cr_out_arr[i].eq(cr_arr[i])

        # Generate the mask for mtcrf, mtocrf, and mfocrf
        # replicate every fxm field in the insn to 4-bit, as a mask
        FXM = xfx_fields.FXM[0:-1]
        mask = Signal(32, reset_less=True)
        comb += mask.eq(Cat(*[Repl(FXM[i], 4) for i in range(8)]))

        #################################
        ##### main switch statement #####

        with m.Switch(op.insn_type):
            ##### mcrf #####
            with m.Case(InternalOp.OP_MCRF):
                # MCRF copies the 4 bits of crA to crB (for instance
                # copying cr2 to cr1)
                BF = xl_fields.BF[0:-1]   # destination CR
                BFA = xl_fields.BFA[0:-1] # source CR
                bf = Signal(BF.shape(), reset_less=True)
                bfa = Signal(BFA.shape(), reset_less=True)
                # use temporary signals because ilang output is insane otherwise
                comb += bf.eq(BF)
                comb += bfa.eq(BFA)

                for i in range(4):
                    idx = Signal(2, name="idx%s" % i, reset_less=True)
                    comb += idx.eq(bf*4+1)
                    comb += cr_out_arr[idx].eq(cr_arr[idx])

            ##### crand, cror, crnor etc. #####
            with m.Case(InternalOp.OP_CROP):
                # crand/cror and friends get decoded to the same opcode, but
                # one of the fields inside the instruction is a 4 bit lookup
                # table. This lookup table gets indexed by bits a and b from
                # the CR to determine what the resulting bit should be.

                # Grab the lookup table for cr_op type instructions
                lut = Signal(4, reset_less=True)
                # There's no field, just have to grab it directly from the insn
                comb += lut.eq(op.insn[6:10])

                # Get the bit selector fields from the instruction
                BT = xl_fields.BT[0:-1]
                BA = xl_fields.BA[0:-1]
                BB = xl_fields.BB[0:-1]
                bt = Signal(BT.shape(), reset_less=True)
                ba = Signal(BA.shape(), reset_less=True)
                bb = Signal(BB.shape(), reset_less=True)
                # use temporary signals because ilang output is insane otherwise
                # also when accessing LUT
                comb += bt.eq(BT)
                comb += ba.eq(BA)
                comb += bb.eq(BB)

                # Extract the two input bits from the CR
                bit_a = Signal(reset_less=True)
                bit_b = Signal(reset_less=True)
                comb += bit_a.eq(cr_arr[ba])
                comb += bit_b.eq(cr_arr[bb])

                # Use the two input bits to look up the result in the LUT
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
                comb += cr_o.eq((a[0:32] & mask) | (cr & ~mask))

            ##### mfcr #####
            with m.Case(InternalOp.OP_MFCR):
                # Ugh. mtocrf and mtcrf have one random bit differentiating
                # them. This bit is not in any particular field, so this
                # extracts that bit from the instruction
                move_one = Signal(reset_less=True)
                comb += move_one.eq(op.insn[20])

                # mfocrf
                with m.If(move_one):
                    comb += self.o.o.eq(cr & mask) # output register RT
                # mfcrf
                with m.Else():
                    comb += self.o.o.eq(cr)        # output register RT

        # output and context
        comb += self.o.cr.eq(cr_o)
        comb += self.o.ctx.eq(self.i.ctx)

        return m
