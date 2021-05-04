from nmigen import Elaboratable, Module, Signal, Shape, unsigned, Cat, Mux
from nmigen import Record, Memory
from nmigen import Const
from soc.fu.mmu.pipe_data import MMUInputData, MMUOutputData, MMUPipeSpec
from nmutil.singlepipe import ControlBase
from nmutil.util import rising_edge

from soc.experiment.mmu import MMU
from soc.experiment.dcache import DCache

from openpower.consts import MSR
from openpower.decoder.power_fields import DecodeFields
from openpower.decoder.power_fieldsn import SignalBitRange
from openpower.decoder.power_decoder2 import decode_spr_num
from openpower.decoder.power_enums import MicrOp, XER_bits

from soc.experiment.pimem import PortInterface
from soc.experiment.pimem import PortInterfaceBase

from soc.experiment.mem_types import LoadStore1ToDCacheType, LoadStore1ToMMUType
from soc.experiment.mem_types import DCacheToLoadStore1Type, MMUToLoadStore1Type

from soc.minerva.wishbone import make_wb_layout
from soc.bus.sram import SRAM


# glue logic for microwatt mmu and dcache
class LoadStore1(PortInterfaceBase):
    def __init__(self, pspec):
        self.pspec = pspec
        self.disable_cache = (hasattr(pspec, "disable_cache") and
                              pspec.disable_cache == True)
        regwid = pspec.reg_wid
        addrwid = pspec.addr_wid

        super().__init__(regwid, addrwid)
        self.dcache = DCache()
        self.d_in  = self.dcache.d_in
        self.d_out = self.dcache.d_out
        self.l_in  = LoadStore1ToMMUType()
        self.l_out = MMUToLoadStore1Type()
        # TODO microwatt
        self.mmureq = Signal()
        self.derror = Signal()

        # TODO, convert dcache wb_in/wb_out to "standard" nmigen Wishbone bus
        self.dbus = Record(make_wb_layout(pspec))

        # for creating a single clock blip to DCache
        self.d_valid = Signal()
        self.d_w_data = Signal(64) # XXX
        self.d_w_valid = Signal()
        self.d_validblip = Signal()

    def set_wr_addr(self, m, addr, mask):
        # this gets complicated: actually a FSM is needed which
        # first checks dcache, then if that fails (in virt mode)
        # it checks the MMU instead.
        #m.d.comb += self.l_in.valid.eq(1)
        #m.d.comb += self.l_in.addr.eq(addr)
        #m.d.comb += self.l_in.load.eq(0)
        m.d.comb += self.d_in.load.eq(0)
        m.d.comb += self.d_in.byte_sel.eq(mask)
        m.d.comb += self.d_in.addr.eq(addr)
        # option to disable the cache entirely for write
        if self.disable_cache:
            m.d.comb += self.d_in.nc.eq(1)
        return None

    def set_rd_addr(self, m, addr, mask):
        # this gets complicated: actually a FSM is needed which
        # first checks dcache, then if that fails (in virt mode)
        # it checks the MMU instead.
        #m.d.comb += self.l_in.valid.eq(1)
        #m.d.comb += self.l_in.load.eq(1)
        #m.d.comb += self.l_in.addr.eq(addr)
        m.d.comb += self.d_valid.eq(1)
        m.d.comb += self.d_in.valid.eq(self.d_validblip)
        m.d.comb += self.d_in.load.eq(1)
        m.d.comb += self.d_in.byte_sel.eq(mask)
        m.d.comb += self.d_in.addr.eq(addr)
        # BAD HACK! disable cacheing on LD when address is 0xCxxx_xxxx
        # this is for peripherals. same thing done in Microwatt loadstore1.vhdl
        with m.If(addr[28:] == Const(0xc, 4)):
            m.d.comb += self.d_in.nc.eq(1)
        # option to disable the cache entirely for read
        if self.disable_cache:
            m.d.comb += self.d_in.nc.eq(1)
        return None #FIXME return value

    def set_wr_data(self, m, data, wen):
        # do the "blip" on write data
        m.d.comb += self.d_valid.eq(1)
        m.d.comb += self.d_in.valid.eq(self.d_validblip)
        # put data into comb which is picked up in main elaborate()
        m.d.comb += self.d_w_valid.eq(1)
        m.d.comb += self.d_w_data.eq(data)
        #m.d.sync += self.d_in.byte_sel.eq(wen) # this might not be needed
        st_ok = self.d_out.valid # TODO indicates write data is valid
        #st_ok = Const(1, 1)
        return st_ok

    def get_rd_data(self, m):
        ld_ok = self.d_out.valid # indicates read data is valid
        data = self.d_out.data   # actual read data
        return data, ld_ok

    """
    if d_in.error = '1' then
                if d_in.cache_paradox = '1' then
                    -- signal an interrupt straight away
                    exception := '1';
                    dsisr(63 - 38) := not r2.req.load;
                    -- XXX there is no architected bit for this
                    -- (probably should be a machine check in fact)
                    dsisr(63 - 35) := d_in.cache_paradox;
                else
                    -- Look up the translation for TLB miss
                    -- and also for permission error and RC error
                    -- in case the PTE has been updated.
                    mmureq := '1';
                    v.state := MMU_LOOKUP;
                    v.stage1_en := '0';
                end if;
            end if;
    """

    def elaborate(self, platform):
        m = super().elaborate(platform)
        comb = m.d.comb

        # create dcache module
        m.submodules.dcache = dcache = self.dcache

        # temp vars
        d_out, l_out, dbus = self.d_out, self.l_out, self.dbus

        with m.If(d_out.error):
            with m.If(d_out.cache_paradox):
                comb += self.derror.eq(1)
                #  dsisr(63 - 38) := not r2.req.load;
                #    -- XXX there is no architected bit for this
                #    -- (probably should be a machine check in fact)
                #    dsisr(63 - 35) := d_in.cache_paradox;
            with m.Else():
                # Look up the translation for TLB miss
                # and also for permission error and RC error
                # in case the PTE has been updated.
                comb += self.mmureq.eq(1)
                # v.state := MMU_LOOKUP;
                # v.stage1_en := '0';

        exc = self.pi.exc_o

        #happened, alignment, instr_fault, invalid,
        comb += exc.happened.eq(d_out.error | l_out.err)
        comb += exc.invalid.eq(l_out.invalid)

        #badtree, perm_error, rc_error, segment_fault
        comb += exc.badtree.eq(l_out.badtree)
        comb += exc.perm_error.eq(l_out.perm_error)
        comb += exc.rc_error.eq(l_out.rc_error)
        comb += exc.segment_fault.eq(l_out.segerr)

        # TODO connect those signals somewhere
        #print(d_out.valid)         -> no error
        #print(d_out.store_done)    -> no error
        #print(d_out.cache_paradox) -> ?
        #print(l_out.done)          -> no error

        # TODO some exceptions set SPRs

        # TODO, connect dcache wb_in/wb_out to "standard" nmigen Wishbone bus
        comb += dbus.adr.eq(dcache.wb_out.adr)
        comb += dbus.dat_w.eq(dcache.wb_out.dat)
        comb += dbus.sel.eq(dcache.wb_out.sel)
        comb += dbus.cyc.eq(dcache.wb_out.cyc)
        comb += dbus.stb.eq(dcache.wb_out.stb)
        comb += dbus.we.eq(dcache.wb_out.we)

        comb += dcache.wb_in.dat.eq(dbus.dat_r)
        comb += dcache.wb_in.ack.eq(dbus.ack)
        if hasattr(dbus, "stall"):
            comb += dcache.wb_in.stall.eq(dbus.stall)

        # create a blip (single pulse) on valid read/write request
        m.d.comb += self.d_validblip.eq(rising_edge(m, self.d_valid))

        # write out d data only when flag set
        with m.If(self.d_w_valid):
            m.d.sync += self.d_in.data.eq(self.d_w_data)
        with m.Else():
            m.d.sync += self.d_in.data.eq(0)

        return m

    def ports(self):
        yield from super().ports()
        # TODO: memory ports


class TestSRAMLoadStore1(LoadStore1):
    def __init__(self, pspec):
        super().__init__(pspec)
        pspec = self.pspec
        # small 32-entry Memory
        if (hasattr(pspec, "dmem_test_depth") and
                isinstance(pspec.dmem_test_depth, int)):
            depth = pspec.dmem_test_depth
        else:
            depth = 32
        print("TestSRAMBareLoadStoreUnit depth", depth)

        self.mem = Memory(width=pspec.reg_wid, depth=depth)

    def elaborate(self, platform):
        m = super().elaborate(platform)
        comb = m.d.comb
        m.submodules.sram = sram = SRAM(memory=self.mem, granularity=8,
                                        features={'cti', 'bte', 'err'})
        dbus = self.dbus

        # directly connect the wishbone bus of LoadStoreUnitInterface to SRAM
        # note: SRAM is a target (slave), dbus is initiator (master)
        fanouts = ['dat_w', 'sel', 'cyc', 'stb', 'we', 'cti', 'bte']
        fanins = ['dat_r', 'ack', 'err']
        for fanout in fanouts:
            print("fanout", fanout, getattr(sram.bus, fanout).shape(),
                  getattr(dbus, fanout).shape())
            comb += getattr(sram.bus, fanout).eq(getattr(dbus, fanout))
            comb += getattr(sram.bus, fanout).eq(getattr(dbus, fanout))
        for fanin in fanins:
            comb += getattr(dbus, fanin).eq(getattr(sram.bus, fanin))
        # connect address
        comb += sram.bus.adr.eq(dbus.adr)

        return m


class FSMMMUStage(ControlBase):
    """FSM MMU

    FSM-based MMU: must call set_ldst_interface and pass in an instance
    of a LoadStore1.  this to comply with the ConfigMemoryPortInterface API
    """
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

        # make life a bit easier in Core XXX mustn't really do this,
        # pspec is designed for config variables, rather than passing
        # things around.  have to think about it, design a way to do
        # it that makes "sense"
        # comment out for now self.pspec.mmu = self.mmu
        # comment out for now self.pspec.dcache = self.dcache

        # debugging output for gtkw
        self.debug0 = Signal(4)
        self.illegal = Signal()

        # for SPR field number access
        i = self.p.data_i
        self.fields = DecodeFields(SignalBitRange, [i.ctx.op.insn])
        self.fields.create_specs()

    def set_ldst_interface(self, ldst):
        """must be called back in Core, after FUs have been set up.
        one of those will be the MMU (us!) but the LoadStore1 instance
        must be set up in ConfigMemoryPortInterface. sigh.
        """
        # incoming PortInterface
        self.ldst = ldst
        self.dcache = self.ldst.dcache
        self.pi = self.ldst.pi

    def elaborate(self, platform):
        assert hasattr(self, "dcache"), "remember to call set_ldst_interface"
        m = super().elaborate(platform)
        comb = m.d.comb
        dcache = self.dcache

        # link mmu and dcache together
        m.submodules.mmu = mmu = self.mmu
        ldst = self.ldst # managed externally: do not add here
        m.d.comb += dcache.m_in.eq(mmu.d_out) # MMUToDCacheType
        m.d.comb += mmu.d_in.eq(dcache.m_out) # DCacheToMMUType

        l_in, l_out = mmu.l_in, mmu.l_out
        d_in, d_out = dcache.d_in, dcache.d_out
        wb_out, wb_in = dcache.wb_out, dcache.wb_in

        # link ldst and MMU together
        comb += l_in.eq(ldst.l_in)
        comb += ldst.l_out.eq(l_out)

        data_i, data_o = self.p.data_i, self.n.data_o
        a_i, b_i, o, spr1_o = data_i.ra, data_i.rb, data_o.o, data_o.spr1
        op = data_i.ctx.op
        msr_i = op.msr
        spr1_i = data_i.spr1

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

        # based on MSR bits, set priv and virt mode.  TODO: 32-bit mode
        comb += d_in.priv_mode.eq(~msr_i[MSR.PR])
        comb += d_in.virt_mode.eq(msr_i[MSR.DR])
        #comb += d_in.mode_32bit.eq(msr_i[MSR.SF]) # ?? err

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
                with m.Case(MicrOp.OP_MTSPR):
                    # despite redirection this FU **MUST** behave exactly
                    # like the SPR FU.  this **INCLUDES** updating the SPR
                    # regfile because the CSV file entry for OP_MTSPR
                    # categorically defines and requires the expectation
                    # that the CompUnit **WILL** write to the regfile.
                    comb += spr1_o.data.eq(spr)
                    comb += spr1_o.ok.eq(1)
                    # subset SPR: first check a few bits
                    with m.If(~spr[9] & ~spr[5]):
                        comb += self.debug0.eq(3)
                        #if matched update local cached value
                        with m.If(spr[0]):
                            sync += dsisr.eq(a_i[:32])
                        with m.Else():
                            sync += dar.eq(a_i)
                        comb += done.eq(1)
                    # pass it over to the MMU instead
                    with m.Else():
                        comb += self.debug0.eq(4)
                        # blip the MMU and wait for it to complete
                        comb += valid.eq(1)   # start "pulse"
                        comb += l_in.valid.eq(blip)   # start
                        comb += l_in.mtspr.eq(1)      # mtspr mode
                        comb += l_in.sprn.eq(spr)  # which SPR
                        comb += l_in.rs.eq(a_i)    # incoming operand (RS)
                        comb += done.eq(1) # FIXME l_out.done

                with m.Case(MicrOp.OP_MFSPR):
                    # subset SPR: first check a few bits
                    #with m.If(~spr[9] & ~spr[5]):
                    #    comb += self.debug0.eq(5)
                        #with m.If(spr[0]):
                        #    comb += o.data.eq(dsisr)
                        #with m.Else():
                        #    comb += o.data.eq(dar)
                    #do NOT return cached values
                    comb += o.data.eq(spr1_i)
                    comb += o.ok.eq(1)
                    comb += done.eq(1)
                    # pass it over to the MMU instead
                    #with m.Else():
                    #    comb += self.debug0.eq(6)
                    #    # blip the MMU and wait for it to complete
                    #    comb += valid.eq(1)   # start "pulse"
                    #    comb += l_in.valid.eq(blip)   # start
                    #    comb += l_in.mtspr.eq(0)   # mfspr!=mtspr
                    #    comb += l_in.sprn.eq(spr)  # which SPR
                    #    comb += l_in.rs.eq(a_i)    # incoming operand (RS)
                    #    comb += o.data.eq(l_out.sprval) # SPR from MMU
                    #    comb += o.ok.eq(l_out.done) # only when l_out valid
                    #    comb += done.eq(1) # FIXME l_out.done

                # XXX this one is going to have to go through LDSTCompUnit
                # because it's LDST that has control over dcache
                # (through PortInterface).  or, another means is devised
                # so as not to have double-drivers of d_in.valid and addr
                #
                #with m.Case(MicrOp.OP_DCBZ):
                #    # activate dcbz mode (spec: v3.0B p850)
                #    comb += valid.eq(1)   # start "pulse"
                #    comb += d_in.valid.eq(blip)     # start
                #    comb += d_in.dcbz.eq(1)         # dcbz mode
                #    comb += d_in.addr.eq(a_i + b_i) # addr is (RA|0) + RB
                #    comb += done.eq(d_out.store_done)     # TODO
                #    comb += self.debug0.eq(1)

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

                with m.Case(MicrOp.OP_ILLEGAL):
                    comb += self.illegal.eq(1)

            with m.If(self.n.ready_i & self.n.valid_o):
                m.d.sync += busy.eq(0)

        return m

    def __iter__(self):
        yield from self.p
        yield from self.n

    def ports(self):
        return list(self)
