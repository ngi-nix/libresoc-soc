"""PortInterface to LoadStoreUnitInterface adapter

    PortInterface   LoadStoreUnitInterface
    -------------   ----------------------

    is_ld_i/1       x_ld_i
    is_st_i/1       x_st_i

    data_len/4      x_mask/16  (translate using LenExpand)

    busy_o/1        most likely to be x_busy_o
    go_die_i/1      rst?
    addr.data/48    x_addr_i (x_addr_i[:4] goes into LenExpand)
    addr.ok/1       probably x_valid_i & ~x_stall_i

    addr_ok_o/1     no equivalent.  *might* work using x_stall_i
    exc_o/6(?)      m_load_err_o and m_store_err_o

    ld.data/64      m_ld_data_o
    ld.ok/1         probably implicit, when x_busy drops low
    st.data/64      x_st_data_i
    st.ok/1         probably kinda redundant, set to x_st_i
"""

from soc.minerva.units.loadstore import LoadStoreUnitInterface
from soc.experiment.pimem import PortInterface
from soc.scoreboard.addr_match import LenExpand
from soc.experiment.pimem import PortInterfaceBase
from nmigen.utils import log2_int

from nmigen import Elaboratable, Module, Signal
from nmutil.latch import SRLatch
from nmutil.util import rising_edge



class Pi2LSUI(PortInterfaceBase):

    def __init__(self, name, lsui=None,
                 data_wid=64, mask_wid=8, addr_wid=48):
        print("pi2lsui reg mask addr", data_wid, mask_wid, addr_wid)
        super().__init__(data_wid, addr_wid)
        if lsui is None:
            lsui = LoadStoreUnitInterface(addr_wid, self.addrbits, data_wid)
        self.lsui = lsui
        self.lsui_busy = Signal()
        self.valid_l = SRLatch(False, name="valid")

    def set_wr_addr(self, m, addr, mask):
        m.d.comb += self.valid_l.s.eq(1)
        m.d.comb += self.lsui.x_mask_i.eq(mask)
        m.d.comb += self.lsui.x_addr_i.eq(addr)

    def set_rd_addr(self, m, addr, mask):
        m.d.comb += self.valid_l.s.eq(1)
        m.d.comb += self.lsui.x_mask_i.eq(mask)
        m.d.comb += self.lsui.x_addr_i.eq(addr)

    def set_wr_data(self, m, data, wen):  # mask already done in addr setup
        m.d.comb += self.lsui.x_st_data_i.eq(data)
        return (~(self.lsui.x_busy_o | self.lsui_busy))

    def get_rd_data(self, m):
        return self.lsui.m_ld_data_o, ~self.lsui_busy

    def elaborate(self, platform):
        m = super().elaborate(platform)
        pi, lsui, addrbits = self.pi, self.lsui, self.addrbits

        m.submodules.valid_l = self.valid_l
        ld_in_progress = Signal()

        # pass ld/st through to LSUI
        m.d.comb += lsui.x_ld_i.eq(pi.is_ld_i)
        m.d.comb += lsui.x_st_i.eq(pi.is_st_i)

        # ooo how annoying.  x_busy_o is set synchronously, i.e. one
        # clock too late for this converter to "notice".  consequently,
        # when trying to wait for ld/st, here: on the first cycle
        # it goes "oh, x_busy_o isn't set, the ld/st must have been
        # completed already, we must be done" when in fact it hasn't
        # started.  to "fix" that we actually have to have a full FSM
        # tracking from when LD/ST starts, right the way through. sigh.
        # first clock busy signal.  needed because x_busy_o is sync
        with m.FSM() as fsm:
            with m.State("IDLE"):
                # detect when ld/st starts.  set busy *immediately*
                with m.If((pi.is_ld_i | pi.is_st_i) & self.valid_l.q):
                    m.d.comb += self.lsui_busy.eq(1)
                    m.next = "BUSY"
            with m.State("BUSY"):
                # detect when busy drops: must then wait for ld/st to end..
                #m.d.comb += self.lsui_busy.eq(self.lsui.x_busy_o)
                m.d.comb += self.lsui_busy.eq(1)
                with m.If(~self.lsui.x_busy_o):
                    m.next = "WAITDEASSERT"
            with m.State("WAITDEASSERT"):
                # when no longer busy: back to start
                with m.If(~pi.is_st_i & ~pi.busy_o):
                    m.next = "IDLE"

        # indicate valid at both ends. OR with lsui_busy (stops comb loop)
        m.d.comb += self.lsui.m_valid_i.eq(self.valid_l.q )
        m.d.comb += self.lsui.x_valid_i.eq(self.valid_l.q )

        # reset the valid latch when not busy.  sync to stop loop
        lsui_active = Signal()
        m.d.comb += lsui_active.eq(~self.lsui.x_busy_o)
        m.d.comb += self.valid_l.r.eq(rising_edge(m, lsui_active))

        return m


class Pi2LSUI1(Elaboratable):

    def __init__(self, name, pi=None, lsui=None,
                 data_wid=64, mask_wid=8, addr_wid=48):
        print("pi2lsui reg mask addr", data_wid, mask_wid, addr_wid)
        self.addrbits = mask_wid
        if pi is None:
            piname = "%s_pi" % name
            pi = PortInterface(piname, regwid=data_wid, addrwid=addr_wid)
        self.pi = pi
        if lsui is None:
            lsui = LoadStoreUnitInterface(addr_wid, self.addrbits, data_wid)
        self.lsui = lsui

    def splitaddr(self, addr):
        """split the address into top and bottom bits of the memory granularity
        """
        return addr[:self.addrbits], addr[self.addrbits:]

    def connect_port(self, inport):
        return self.pi.connect_port(inport)

    def elaborate(self, platform):
        m = Module()
        pi, lsui, addrbits = self.pi, self.lsui, self.addrbits
        m.submodules.lenexp = lenexp = LenExpand(log2_int(self.addrbits), 8)

        ld_in_progress = Signal(reset=0)
        st_in_progress = Signal(reset=0)

        m.d.comb += lsui.x_ld_i.eq(pi.is_ld_i)
        m.d.comb += lsui.x_st_i.eq(pi.is_st_i)
        m.d.comb += pi.busy_o.eq(pi.is_ld_i | pi.is_st_i)  # lsui.x_busy_o)

        lsbaddr, msbaddr = self.splitaddr(pi.addr.data)
        m.d.comb += lenexp.len_i.eq(pi.data_len)
        m.d.comb += lenexp.addr_i.eq(lsbaddr)  # LSBs of addr
        m.d.comb += lsui.x_addr_i.eq(pi.addr.data)  # XXX hmmm...

        with m.If(pi.addr.ok):
            # expand the LSBs of address plus LD/ST len into 16-bit mask
            m.d.comb += lsui.x_mask_i.eq(lenexp.lexp_o)
            # pass through the address, indicate "valid"
            m.d.comb += lsui.x_valid_i.eq(1)
            # indicate "OK" - XXX should be checking address valid
            m.d.comb += pi.addr_ok_o.eq(1)

        with m.If(~lsui.x_busy_o & pi.is_st_i & pi.addr.ok):
            m.d.sync += st_in_progress.eq(1)

        with m.If(pi.is_ld_i):
            # shift/mask out the loaded data
            m.d.comb += pi.ld.data.eq((lsui.m_ld_data_o & lenexp.rexp_o) >>
                                      (lenexp.addr_i*8))
            # remember we're in the process of loading
            with m.If(pi.addr.ok):
                m.d.sync += ld_in_progress.eq(1)

        # If a load happened on the previous cycle and the memory is
        # not busy, that means it returned the data from the load. In
        # that case ld.ok should be set andwe can clear the
        # ld_in_progress flag
        with m.If(ld_in_progress & ~lsui.x_busy_o):
            m.d.comb += pi.ld.ok.eq(1)
            m.d.sync += ld_in_progress.eq(0)
        with m.Else():
            m.d.comb += pi.ld.ok.eq(0)

        with m.If(pi.is_st_i & pi.st.ok):
            m.d.comb += lsui.x_st_data_i.eq(pi.st.data << (lenexp.addr_i*8))
            with m.If(st_in_progress):
                m.d.sync += st_in_progress.eq(0)
            with m.Else():
                m.d.comb += pi.busy_o.eq(0)

        return m
