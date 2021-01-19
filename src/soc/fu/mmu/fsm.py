from nmigen import Elaboratable, Module, Signal, Shape, unsigned, Cat, Mux
from nmigen import Const
from soc.fu.mmu.pipe_data import MMUInputData, MMUOutputData, MMUPipeSpec
from nmutil.singlepipe import ControlBase
from nmutil.util import rising_edge

from soc.experiment.mmu import MMU
from soc.experiment.dcache import DCache

from soc.decoder.power_fields import DecodeFields
from soc.decoder.power_fieldsn import SignalBitRange
from soc.decoder.power_decoder2 import decode_spr_num
from soc.decoder.power_enums import MicrOp, SPR, XER_bits

from soc.experiment.pimem import PortInterface
from soc.experiment.pimem import PortInterfaceBase

from soc.experiment.mem_types import LoadStore1ToDCacheType, LoadStore1ToMMUType
from soc.experiment.mem_types import DCacheToLoadStore1Type, MMUToLoadStore1Type

# for testing purposes
from soc.experiment.testmem import TestMemory

# glue logic for microwatt mmu and dcache
class LoadStore1(PortInterfaceBase):
    def __init__(self, regwid=64, addrwid=4):
        super().__init__(regwid, addrwid)
        self.d_in  = LoadStore1ToDCacheType()
        self.d_out = DCacheToLoadStore1Type()
        self.l_in  = LoadStore1ToMMUType()
        self.l_out = MMUToLoadStore1Type()
        # for debugging with gtkwave only
        self.debug1 = Signal()
        self.debug2 = Signal()

    def set_wr_addr(self, m, addr, mask):
        #m.d.comb += self.d_in.valid.eq(1)
        #m.d.comb += self.l_in.valid.eq(1)
        #m.d.comb += self.d_in.load.eq(0)
        #m.d.comb += self.l_in.load.eq(0)
        m.d.comb += self.d_in.addr.eq(addr)
        m.d.comb += self.l_in.addr.eq(addr)
        # TODO set mask
        return None

    def set_rd_addr(self, m, addr, mask):
        m.d.comb += self.d_in.valid.eq(1)
        m.d.comb += self.l_in.valid.eq(1)
        m.d.comb += self.d_in.load.eq(1)
        m.d.comb += self.l_in.load.eq(1)
        m.d.comb += self.d_in.addr.eq(addr)
        m.d.comb += self.l_in.addr.eq(addr)
        m.d.comb += self.debug1.eq(1)
        # m.d.comb += self.debug2.eq(1)
        # connect testmem first
        return None #FIXME return value

    def set_wr_data(self, m, data, wen):
        m.d.comb += self.d_in.data.eq(data)
        # TODO set wen
        st_ok = Const(1, 1)
        return st_ok

    def get_rd_data(self, m):
        ld_ok = Const(1, 1)
        data = self.d_out.data
        return data, ld_ok

    def elaborate(self, platform):
        m = super().elaborate(platform)

        d_out = self.d_out
        l_out = self.l_out

        exc = self.pi.exception_o

        #happened, alignment, instr_fault, invalid,
        m.d.comb += exc.happened.eq(d_out.error | l_out.err)
        m.d.comb += exc.invalid.eq(l_out.invalid)

        #badtree, perm_error, rc_error, segment_fault
        m.d.comb += exc.badtree.eq(l_out.badtree)
        m.d.comb += exc.perm_error.eq(l_out.perm_error)
        m.d.comb += exc.rc_error.eq(l_out.rc_error)
        m.d.comb += exc.segment_fault.eq(l_out.segerr)

        # TODO connect those signals somewhere
        #print(d_out.valid)         -> no error
        #print(d_out.store_done)    -> no error
        #print(d_out.cache_paradox) -> ?
        #print(l_out.done)          -> no error

        # TODO some exceptions set SPRs

        return m

    def ports(self):
        yield from super().ports()
        # TODO: memory ports

class FSMMMUStage(ControlBase):
    def __init__(self, pspec):
        super().__init__()
        self.pspec = pspec

        # set up p/n data
        self.p.data_i = MMUInputData(pspec)
        self.n.data_o = MMUOutputData(pspec)

        # incoming PortInterface
        self.ldst = LoadStore1()       # TODO make this depend on pspec
        self.pi = self.ldst.pi

        # this Function Unit is extremely unusual in that it actually stores a
        # "thing" rather than "processes inputs and produces outputs".  hence
        # why it has to be a FSM.  linking up LD/ST however is going to have
        # to be done back in Issuer (or Core)

        self.mmu = MMU()
        self.dcache = DCache()
        regwid=64
        aw = 5
        # for verification of DCache
        # TODO: create connection to real memory, backend memory interface
        self.testmem = TestMemory(regwid, aw, granularity=regwid//8, init=False)

        # make life a bit easier in Core
        self.pspec.mmu = self.mmu
        self.pspec.dcache = self.dcache

        # debugging output for gtkw
        self.debug0 = Signal(4)
        self.debug_wb_cyc = Signal()
        self.debug_wb_stb = Signal()
        self.debug_wb_we = Signal()
        #self.debug1 = Signal(64)
        #self.debug2 = Signal(64)
        #self.debug3 = Signal(64)

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
        m.submodules.ldst = ldst = self.ldst
        m.submodules.testmem = testmem = self.testmem
        m.d.comb += dcache.m_in.eq(mmu.d_out)
        m.d.comb += mmu.d_in.eq(dcache.m_out)
        l_in, l_out = mmu.l_in, mmu.l_out
        d_in, d_out = dcache.d_in, dcache.d_out
        wb_out, wb_in = dcache.wb_out, dcache.wb_in

        # link ldst and dcache together
        comb += l_in.eq(self.ldst.l_in)
        comb += self.ldst.l_out.eq(l_out)
        comb += d_in.eq(self.ldst.d_in)
        comb += self.ldst.d_out.eq(self.dcache.d_out)

        #connect read port
        rdport = self.testmem.rdport
        comb += rdport.addr.eq(wb_out.adr)
        comb += wb_in.dat.eq(rdport.data)

        #connect write port
        wrport = self.testmem.wrport
        comb += wrport.addr.eq(wb_out.adr)
        comb += wrport.data.eq(wb_out.dat) # write st to mem
        comb += wrport.en.eq(wb_out.cyc & wb_out.we) # enable writes

        # connect DCache wishbone master to debugger
        comb += self.debug_wb_cyc.eq(wb_out.cyc)
        comb += self.debug_wb_stb.eq(wb_out.stb)
        comb += self.debug_wb_we.eq(wb_out.we)

        comb += wb_in.stall.eq(0)
        # testmem only takes on cycle
        with m.If( wb_out.cyc ):
            m.d.sync += wb_in.ack.eq( wb_out.stb )

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

            # FIXME: properly implement MicrOp.OP_MTSPR and MicrOp.OP_MFSPR

            with m.Switch(op.insn_type):
                comb += self.debug0.eq(3)
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
                    comb += self.debug0.eq(3)
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
                        comb += l_in.mtspr.eq(0)   # mfspr!=mtspr
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
                    comb += done.eq(d_out.store_done)     # TODO
                    comb += self.debug0.eq(1)

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
                    comb += self.debug0.eq(2)

            with m.If(self.n.ready_i & self.n.valid_o):
                m.d.sync += busy.eq(0)

        return m

    def __iter__(self):
        yield from self.p
        yield from self.n

    def ports(self):
        return list(self)
