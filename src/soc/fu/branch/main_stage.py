# License: LGPLv3
# Copyright (C) 2020 Luke Kenneth Casson Leighton <lkcl@lkcl.net>
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>

"""Branch Pipeline

This stage is intended to do most of the work of executing branch
instructions. This is OP_B, OP_B, OP_BCREG

Note: it is PARTICULARLY important to pay attention to PowerDecode2
more specifically DecodeRA etc. as these work closely in conjunction
with the Branch pipeline, here.

The Branch pipeline itself does not and cannot read registers: it can
only process data and produce results.  Therefore, something else needs
to know that BC needs CTR, and that one of the outputs from here is to
go into LR, and so on.  Encoding of which registers are read and written
is the responsibility of PowerDecode2 and because some of those decisions
are conditional (based on BO2 for example) PowerDecode2 has to duplicate
some of that bitlevel operand field decoding.

It us therefore quite critical to read this code in conjunction side by
side with power_decode2.py

Links:
* https://bugs.libre-soc.org/show_bug.cgi?id=313
* https://bugs.libre-soc.org/show_bug.cgi?id=335
* https://libre-soc.org/openpower/isa/branch/
"""

from nmigen import (Module, Signal, Cat, Mux, Const, Array)
from nmutil.pipemodbase import PipeModBase
from nmutil.extend import exts
from soc.fu.branch.pipe_data import BranchInputData, BranchOutputData
from openpower.decoder.power_enums import MicrOp

from openpower.decoder.power_fields import DecodeFields
from openpower.decoder.power_fieldsn import SignalBitRange


def br_ext(bd):
    """computes sign-extended NIA (assumes word-alignment)
    """
    return Cat(Const(0, 2), exts(bd, bd.shape().width, 64 - 2))


"""
Notes on BO Field:

BO    Description
0000z Decrement the CTR, then branch if decremented CTR[M:63]!=0 and CR[BI]=0
0001z Decrement the CTR, then branch if decremented CTR[M:63]=0 and CR[BI]=0
001at Branch if CR[BI]=0
0100z Decrement the CTR, then branch if decremented CTR[M:63]!=0 and CR[BI]=1
0101z Decrement the CTR, then branch if decremented CTR[M:63]=0 and CR[BI]=1
011at Branch if CR[BI]=1
1a00t Decrement the CTR, then branch if decremented CTR[M:63]!=0
1a01t Decrement the CTR, then branch if decremented CTR[M:63]=0
1z1zz Branch always
"""

class BranchMainStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "main")
        self.fields = DecodeFields(SignalBitRange, [self.i.ctx.op.insn])
        self.fields.create_specs()

    def ispec(self):
        return BranchInputData(self.pspec)

    def ospec(self):
        return BranchOutputData(self.pspec) # TODO: ALUIntermediateData

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        op = self.i.ctx.op
        lk = op.lk # see PowerDecode2 as to why this is done
        cr, cia, ctr, fast1 = self.i.cr, op.cia, self.i.ctr, self.i.fast1
        fast2 = self.i.fast2
        nia_o, lr_o, ctr_o = self.o.nia, self.o.lr, self.o.ctr

        # obtain relevant instruction field AA, "Absolute Address" mode
        i_fields = self.fields.FormI
        AA = i_fields.AA[0:-1]

        br_imm_addr = Signal(64, reset_less=True)
        br_addr = Signal(64, reset_less=True)
        br_taken = Signal(reset_less=True)

        # Handle absolute or relative branches
        with m.If(AA | (op.insn_type == MicrOp.OP_BCREG)):
            comb += br_addr.eq(br_imm_addr)
        with m.Else():
            comb += br_addr.eq(br_imm_addr + cia)

        # fields for conditional branches (BO and BI are same for BC and BCREG)
        b_fields = self.fields.FormB
        BO = b_fields.BO
        BI = b_fields.BI[0:2] # CR0-7 selected already in PowerDecode2.

        cr_bits = Array([cr[3-i] for i in range(4)]) # invert. Because POWER.

        # copy of BO in a signal
        bo = Signal(5, reset_less=True)
        comb += bo.eq(BO[0:5])

        # The bit of CR selected by BI
        bi = Signal(2, reset_less=True)
        cr_bit = Signal(reset_less=True)
        comb += bi.eq(BI)                 # reduces gate-count due to pmux
        comb += cr_bit.eq(cr_bits[bi])

        # Whether ctr is written to on a conditional branch
        ctr_write = Signal(reset_less=True)
        comb += ctr_write.eq(0)

        # Whether the conditional branch should be taken
        bc_taken = Signal(reset_less=True)
        with m.If(bo[2]):
            comb += bc_taken.eq((cr_bit == bo[3]) | bo[4])
        with m.Else():
            # decrement the counter and place into output
            ctr_n = Signal(64, reset_less=True)
            comb += ctr_n.eq(ctr - 1)
            comb += ctr_o.data.eq(ctr_n)
            comb += ctr_write.eq(1)
            # take either all 64 bits or only 32 of post-incremented counter
            ctr_m = Signal(64, reset_less=True)
            with m.If(op.is_32bit):
                comb += ctr_m.eq(ctr[:32])
            with m.Else():
                comb += ctr_m.eq(ctr)
            # check CTR zero/non-zero against bo[1]
            ctr_zero_bo1 = Signal(reset_less=True) # bo[1] == (ctr==0)
            comb += ctr_zero_bo1.eq(bo[1] ^ ctr_n.any())
            with m.If(bo[3:5] == 0b00):
                comb += bc_taken.eq(ctr_zero_bo1 & ~cr_bit)
            with m.Elif(bo[3:5] == 0b01):
                comb += bc_taken.eq(ctr_zero_bo1 & cr_bit)
            with m.Elif(bo[4] == 1):
                comb += bc_taken.eq(ctr_zero_bo1)

        ### Main Switch Statement ###
        with m.Switch(op.insn_type):
            #### branch ####
            with m.Case(MicrOp.OP_B):
                LI = i_fields.LI[0:-1]
                comb += br_imm_addr.eq(br_ext(LI))
                comb += br_taken.eq(1)
            #### branch conditional ####
            with m.Case(MicrOp.OP_BC):
                BD = b_fields.BD[0:-1]
                comb += br_imm_addr.eq(br_ext(BD))
                comb += br_taken.eq(bc_taken)
                comb += ctr_o.ok.eq(ctr_write)
            #### branch conditional reg ####
            with m.Case(MicrOp.OP_BCREG):
                xo = self.fields.FormXL.XO[0:-1]
                with m.If(xo[9] & ~xo[5]):
                    comb += br_imm_addr.eq(Cat(Const(0, 2), fast1[2:]))
                with m.Else():
                    comb += br_imm_addr.eq(Cat(Const(0, 2), fast2[2:]))
                comb += br_taken.eq(bc_taken)
                comb += ctr_o.ok.eq(ctr_write)

        # output next instruction address
        comb += nia_o.data.eq(br_addr)
        comb += nia_o.ok.eq(br_taken)

        # link register - only activate on operations marked as "lk"
        with m.If(lk):
            # ctx.op.lk is the AND of the insn LK field *and* whether the
            # op is to "listen" to the link field
            comb += lr_o.data.eq(cia + 4)
            comb += lr_o.ok.eq(1)

        # and context
        comb += self.o.ctx.eq(self.i.ctx)

        return m
