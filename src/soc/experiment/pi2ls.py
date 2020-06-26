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
    addr_exc_o/2(?) m_load_err_o and m_store_err_o

    ld.data/64      m_ld_data_o
    ld.ok/1         probably implicit, when x_busy drops low
    st.data/64      x_st_data_i
    st.ok/1         probably kinda redundant, set to x_st_i
"""

from soc.minerva.units.loadstore import LoadStoreUnitInterface
from soc.experiment.pimem import PortInterface
from soc.scoreboard.addr_match import LenExpand
from nmigen.utils import log2_int

from nmigen import Elaboratable, Module, Signal


class Pi2LSUI(Elaboratable):

    def __init__(self, name, pi=None, lsui=None,
                             regwid=64, mask_wid=8, addrwid=48):
        print ("pi2lsui reg mask addr", regwid, mask_wid, addrwid)
        self.addrbits = mask_wid
        if pi is None:
            pi = PortInterface(name="%s_pi", regwid=regwid, addrwid=addrwid)
        self.pi = pi
        if lsui is None:
            lsui = LoadStoreUnitInterface(addrwid, self.addrbits, regwid)
        self.lsui = lsui

    def splitaddr(self, addr):
        """split the address into top and bottom bits of the memory granularity
        """
        return addr[:self.addrbits], addr[self.addrbits:]

    def elaborate(self, platform):
        m = Module()
        pi, lsui, addrbits = self.pi, self.lsui, self.addrbits
        m.submodules.lenexp = lenexp = LenExpand(log2_int(self.addrbits), 8)

        ld_in_progress = Signal(reset=0)

        m.d.comb += lsui.x_ld_i.eq(pi.is_ld_i)
        m.d.comb += lsui.x_st_i.eq(pi.is_st_i)
        m.d.comb += pi.busy_o.eq(lsui.x_busy_o)

        with m.If(pi.addr.ok):
            # expand the LSBs of address plus LD/ST len into 16-bit mask
            lsbaddr, msbaddr = self.splitaddr(pi.addr.data)
            m.d.comb += lenexp.len_i.eq(pi.data_len)
            m.d.comb += lenexp.addr_i.eq(lsbaddr) # LSBs of addr
            m.d.comb += lsui.x_mask_i.eq(lenexp.lexp_o)
            # pass through the address, indicate "valid"
            m.d.comb += lsui.x_addr_i.eq(pi.addr.data) # XXX hmmm...
            m.d.comb += lsui.x_valid_i.eq(1)
            # indicate "OK" - XXX should be checking address valid
            m.d.comb += pi.addr_ok_o.eq(1)

        with m.If(pi.is_ld_i):
            # shift/mask out the loaded data
            m.d.comb += pi.ld.data.eq((lsui.m_ld_data_o & lenexp.rexp_o) >>
                                      (lenexp.addr_i*8))
            # remember we're in the process of loading
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

        return m
