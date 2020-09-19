from nmigen import Elaboratable, Module, Signal, Shape, unsigned, Cat, Mux
from soc.fu.mmu.pipe_data import MMUInputData, MMUOutputData, MMUPipeSpec
from nmutil.singlepipe import ControlBase
from nmutil.util import rising_edge

from soc.experiment.mmu import MMU
from soc.experiment.dcache import DCache

from soc.decoder.power_fields import DecodeFields
from soc.decoder.power_fieldsn import SignalBitRange
from soc.decoder.power_decoder2 import decode_spr_num
from soc.decoder.power_enums import MicrOp, SPR, XER_bits


class FSMMMUStage(ControlBase):
    def __init__(self, pspec):
        super().__init__()
        self.pspec = pspec

        # set up p/n data
        self.p.data_i = MMUInputData(pspec)
        self.n.data_o = MMUOutputData(pspec)

        # this Function Unit is extremely unusual in that it actually stores a
        # "thing" rather than "processes inputs and produces outputs".  hence
        # why it has to be a FSM.  linking up LD/ST however is going to have
        # to be done back in Issuer (or Core)

        self.mmu = MMU()
        self.dcache = DCache()

        # make life a bit easier in Core
        self.pspec.mmu = self.mmu
        self.pspec.dcache = self.dcache

        # for SPR field number access
        i = self.p.data_i
        self.fields = DecodeFields(SignalBitRange, [i.ctx.op.insn])
        self.fields.create_specs()

    def elaborate(self, platform):
        m = super().elaborate(platform)
        comb = m.d.comb

        # link mmu and dcache together
        m.submodules.dcache = dcache = self.dcache
        m.submodules.mmu = mmu = self.mmu
        m.d.comb += dcache.m_in.eq(mmu.d_out)
        m.d.comb += mmu.d_in.eq(dcache.m_out)
        l_in, l_out = mmu.l_in, mmu.l_out
        d_in, d_out = dcache.d_in, dcache.d_out

        data_i, data_o = self.p.data_i, self.n.data_o
        a_i, b_i, o = data_i.ra, data_i.rb, data_o.o
        op = data_i.ctx.op

        # TODO: link these SPRs somewhere
        dsisr = Signal(64)
        dar = Signal(64)

        # busy/done signals
        busy = Signal()
        done = Signal()
        m.d.comb += self.n.valid_o.eq(busy & done)
        m.d.comb += self.p.ready_o.eq(~busy)

        # take copy of X-Form SPR field
        x_fields = self.fields.FormXFX
        spr = Signal(len(x_fields.SPR))
        comb += spr.eq(decode_spr_num(x_fields.SPR))

        # ok so we have to "pulse" the MMU (or dcache) rather than
        # hold the valid hi permanently.  guess what this does...
        valid = Signal()
        blip = Signal()
        m.d.comb += blip.eq(rising_edge(m, valid))

        with m.If(~busy):
            with m.If(self.p.valid_i):
                m.d.sync += busy.eq(1)
        with m.Else():

            # based on the Micro-Op, we work out which of MMU or DCache
            # should "action" the operation.  one of MMU or DCache gets
            # enabled ("valid") and we twiddle our thumbs until it
            # responds ("done").
            with m.Switch(op):

                with m.Case(MicrOp.OP_MTSPR):
                    # subset SPR: first check a few bits
                    with m.If(~spr[9] & ~spr[5]):
                        with m.If(spr[0]):
                            comb += dsisr.eq(a_i[:32])
                        with m.Else():
                            comb += dar.eq(a_i)
                        comb += done.eq(1)
                    # pass it over to the MMU instead
                    with m.Else():
                        # blip the MMU and wait for it to complete
                        comb += valid.eq(1)   # start "pulse"
                        comb += l_in.valid.eq(blip)   # start
                        comb += l_in.mtspr.eq(1)      # mtspr mode
                        comb += l_in.sprn.eq(spr)  # which SPR
                        comb += l_in.rs.eq(a_i)    # incoming operand (RS)
                        comb += done.eq(l_out.done) # zzzz

                with m.Case(MicrOp.OP_MFSPR):
                    # subset SPR: first check a few bits
                    with m.If(~spr[9] & ~spr[5]):
                        with m.If(spr[0]):
                            comb += o.data.eq(dsisr)
                        with m.Else():
                            comb += o.data.eq(dar)
                        comb += o.ok.eq(1)
                        comb += done.eq(1)
                    # pass it over to the MMU instead
                    with m.Else():
                        # blip the MMU and wait for it to complete
                        comb += valid.eq(1)   # start "pulse"
                        comb += l_in.valid.eq(blip)   # start
                        comb += l_in.mtspr.eq(1)   # mtspr mode
                        comb += l_in.sprn.eq(spr)  # which SPR
                        comb += l_in.rs.eq(a_i)    # incoming operand (RS)
                        comb += o.data.eq(l_out.sprval) # SPR from MMU
                        comb += o.ok.eq(l_out.done) # only when l_out valid
                        comb += done.eq(l_out.done) # zzzz

                with m.Case(MicrOp.OP_DCBZ):
                    # activate dcbz mode (spec: v3.0B p850)
                    comb += valid.eq(1)   # start "pulse"
                    comb += d_in.valid.eq(blip)     # start
                    comb += d_in.dcbz.eq(1)         # dcbz mode
                    comb += d_in.addr.eq(a_i + b_i) # addr is (RA|0) + RB
                    comb += done.eq(l_out.done)     # zzzz

                with m.Case(MicrOp.OP_TLBIE):
                    # pass TLBIE request to MMU (spec: v3.0B p1034)
                    # note that the spr is *not* an actual spr number, it's
                    # just that those bits happen to match with field bits
                    # RIC, PRS, R
                    comb += valid.eq(1)   # start "pulse"
                    comb += l_in.valid.eq(blip)   # start
                    comb += l_in.tlbie.eq(1)   # mtspr mode
                    comb += l_in.sprn.eq(spr)  # use sprn to send insn bits
                    comb += l_in.addr.eq(b_i)  # incoming operand (RB)
                    comb += done.eq(l_out.done) # zzzz

            with m.If(self.n.ready_i & self.n.valid_o):
                m.d.sync += busy.eq(0)

        return m

    def __iter__(self):
        yield from self.p
        yield from self.n

    def ports(self):
        return list(self)