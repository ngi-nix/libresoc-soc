"""SPR Pipeline

* https://bugs.libre-soc.org/show_bug.cgi?id=348
* https://libre-soc.org/openpower/isa/sprset/
"""

from nmigen import (Module, Signal, Cat)
from nmutil.pipemodbase import PipeModBase
from soc.fu.spr.pipe_data import SPRInputData, SPROutputData
from openpower.decoder.power_enums import MicrOp, SPRfull, SPRreduced, XER_bits

from openpower.decoder.power_fields import DecodeFields
from openpower.decoder.power_fieldsn import SignalBitRange
from openpower.decoder.power_decoder2 import decode_spr_num


class SPRMainStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "spr_main")
        # test if regfiles are reduced
        self.regreduce_en = (hasattr(pspec, "regreduce") and
                                            (pspec.regreduce == True))

        self.fields = DecodeFields(SignalBitRange, [self.i.ctx.op.insn])
        self.fields.create_specs()

    def ispec(self):
        return SPRInputData(self.pspec)

    def ospec(self):
        return SPROutputData(self.pspec)

    def elaborate(self, platform):
        if self.regreduce_en:
            SPR = SPRreduced
        else:
            SPR = SPRfull
        m = Module()
        comb = m.d.comb
        op = self.i.ctx.op

        # convenience variables
        a_i, spr1_i, fast1_i = self.i.a, self.i.spr1, self.i.fast1
        so_i, ov_i, ca_i = self.i.xer_so, self.i.xer_ov, self.i.xer_ca
        so_o, ov_o, ca_o = self.o.xer_so, self.o.xer_ov, self.o.xer_ca
        o, spr1_o, fast1_o = self.o.o, self.o.spr1, self.o.fast1

        # take copy of D-Form TO field
        x_fields = self.fields.FormXFX
        spr = Signal(len(x_fields.SPR))
        comb += spr.eq(decode_spr_num(x_fields.SPR))

        # TODO: some #defines for the bits n stuff.
        with m.Switch(op.insn_type):
            #### MTSPR ####
            with m.Case(MicrOp.OP_MTSPR):
                with m.Switch(spr):
                    # fast SPRs first
                    with m.Case(SPR.CTR, SPR.LR, SPR.TAR, SPR.SRR0,
                                SPR.SRR1, SPR.XER, SPR.DEC):
                        comb += fast1_o.data.eq(a_i)
                        comb += fast1_o.ok.eq(1)
                        # XER is constructed
                        with m.If(spr == SPR.XER):
                            # sticky
                            comb += so_o.data.eq(a_i[63-XER_bits['SO']])
                            comb += so_o.ok.eq(1)
                            # overflow
                            comb += ov_o.data[0].eq(a_i[63-XER_bits['OV']])
                            comb += ov_o.data[1].eq(a_i[63-XER_bits['OV32']])
                            comb += ov_o.ok.eq(1)
                            # carry
                            comb += ca_o.data[0].eq(a_i[63-XER_bits['CA']])
                            comb += ca_o.data[1].eq(a_i[63-XER_bits['CA32']])
                            comb += ca_o.ok.eq(1)

                    # slow SPRs TODO
                    with m.Default():
                        comb += spr1_o.data.eq(a_i)
                        comb += spr1_o.ok.eq(1)

            # move from SPRs
            with m.Case(MicrOp.OP_MFSPR):
                comb += o.ok.eq(1)
                with m.Switch(spr):
                    # fast SPRs first
                    with m.Case(SPR.CTR, SPR.LR, SPR.TAR, SPR.SRR0, SPR.SRR1,
                                SPR.XER, SPR.DEC, SPR.TB):
                        comb += o.data.eq(fast1_i)
                        with m.If(spr == SPR.XER):
                            # bits 0:31 and 35:43 are treated as reserved
                            # and return 0s when read using mfxer
                            comb += o[32:64].eq(0)       # MBS0 bits 0-31
                            comb += o[63-43:64-35].eq(0) # MSB0 bits 35-43
                            # sticky
                            comb += o[63-XER_bits['SO']].eq(so_i)
                            # overflow
                            comb += o[63-XER_bits['OV']].eq(ov_i[0])
                            comb += o[63-XER_bits['OV32']].eq(ov_i[1])
                            # carry
                            comb += o[63-XER_bits['CA']].eq(ca_i[0])
                            comb += o[63-XER_bits['CA32']].eq(ca_i[1])
                    with m.Case(SPR.TBU):
                        comb += o.data[0:32].eq(fast1_i[32:64])

                    # slow SPRs TODO
                    with m.Default():
                        comb += o.data.eq(spr1_i)

        comb += self.o.ctx.eq(self.i.ctx)

        return m
