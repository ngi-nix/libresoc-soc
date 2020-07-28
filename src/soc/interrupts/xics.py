"""Microwatt xics.vhdl converted to nmigen
#
# This is a simple XICS compliant interrupt controller.  This is a
# Presenter (ICP) and Source (ICS) in two small units directly
# connected to each other with no routing layer.
#
# The sources have a configurable IRQ priority set a set of ICS
# registers in the source units.
#
# The source ids start at 16 for int_level_in(0) and go up from
# there (ie int_level_in(1) is source id 17). XXX Make a generic
#
# The presentation layer will pick an interupt that is more
# favourable than the current CPPR and present it via the XISR and
# send an interrpt to the processor (via e_out). This may not be the
# highest priority interrupt currently presented (which is allowed
# via XICS)
#
"""
from nmigen import Elaboratable, Module, Signal, Cat, Const, Record, Array, Mux
from nmutil.iocontrol import RecordObject
from nmigen.utils import log2_int
from nmigen.cli import rtlil
from soc.minerva.wishbone import make_wb_layout
from nmutil.util import wrap

cxxsim = False
if cxxsim:
    from nmigen.sim.cxxsim import Simulator, Settle
else:
    from nmigen.back.pysim import Simulator, Settle



class ICS2ICP(RecordObject):
    """
        # Level interrupts only, ICS just keeps prsenting the
        # highest priority interrupt. Once handling edge, something
        # smarter involving handshake & reject support will be needed
    """
    def __init__(self, name):
        super().__init__(name=name)
        self.src = Signal(4, reset_less=True)
        self.pri = Signal(8, reset_less=True)

# hardwire the hardware IRQ priority
HW_PRIORITY = Const(0x80, 8)

# 8 bit offsets for each presentation
XIRR_POLL = 0x00
XIRR      = 0x04
RESV0     = 0x08
MFRR      = 0x0c


class RegInternal(RecordObject):
    def __init__(self, name=None):
        super().__init__(name=name)
        self.xisr = Signal(24)
        self.cppr = Signal(8)
        self.mfrr = Signal(8, reset=0xff) # mask everything on reset
        self.irq = Signal(1)
        self.wb_rd_data = Signal(32)
        self.wb_ack = Signal(1)


def bswap(v):
    return Cat(v[24:32], v[16:24], v[8:16], v[0:8])


class XICS_ICP(Elaboratable):

    def __init__(self):
        class Spec: pass
        spec = Spec()
        spec.addr_wid = 30
        spec.mask_wid = 4
        spec.reg_wid = 32
        self.bus = Record(make_wb_layout(spec))
        self.ics_i = ICS2ICP("ics_i")
        self.core_irq_o = Signal()

    def elaborate(self, platform):
        m = Module()
        comb, sync = m.d.comb, m.d.sync

        r = RegInternal()
        r_next = RegInternal()

        sync += r.eq(r_next)
        # We delay core_irq_out by a cycle to help with timing
        sync += self.core_irq_o.eq(r.irq)

        comb += self.bus.dat_r.eq(r.wb_rd_data)
        comb += self.bus.ack.eq(r.wb_ack)

        v = RegInternal()
        xirr_accept_rd = Signal()

        be_in  = Signal(32)
        be_out = Signal(32)

        pending_priority = Signal(8)

        comb += v.eq(r)
        comb += v.wb_ack.eq(0)

        comb += xirr_accept_rd.eq(0)

        comb += be_in.eq(bswap(self.bus.dat_w))
        comb += be_out.eq(0)

        with m.If(self.bus.cyc & self.bus.stb):
            comb += v.wb_ack.eq(1) # always ack
            with m.If(self.bus.we): # write
                # writes to both XIRR are the same
                with m.Switch( self.bus.adr[:8]):
                    with m.Case(XIRR_POLL):
                        # report "ICP XIRR_POLL write";
                        comb += v.cppr.eq(be_in[24:32])
                    with m.Case(XIRR):
                        comb += v.cppr.eq(be_in[24:32])
                        with m.If(self.bus.sel == 0xf): #  # 4 byte
                            #report "ICP XIRR write word (EOI) :" & \
                            #                  to_hstring(be_in);
                            pass
                        with m.Elif(self.bus.sel == 0x1): # 1 byte
                            #report "ICP XIRR write byte (CPPR):" & \
                            #to_hstring(be_in(31 downto 24));
                            pass
                        with m.Else():
                            #report "ICP XIRR UNSUPPORTED write ! sel=" & \
                            #           to_hstring(self.bus.sel);
                            pass
                    with m.Case(MFRR ):
                        comb += v.mfrr.eq(be_in[24:32])
                        with m.If(self.bus.sel == 0xf): #  # 4 byte
                            # report "ICP MFRR write word:" & to_hstring(be_in);
                            pass
                        with m.Elif(self.bus.sel == 0x1): # 1 byte
                            # report "ICP MFRR write byte:" & \
                            #                to_hstring(be_in(31 downto 24));
                            pass
                        with m.Else():
                            # report "ICP MFRR UNSUPPORTED write ! sel=" & \
                            #                to_hstring(self.bus.sel);
                            pass

            with m.Else(): # read

                with m.Switch( self.bus.adr[:8]):
                    with m.Case(XIRR_POLL):
                        # report "ICP XIRR_POLL read";
                        comb += be_out.eq(r.xisr & r.cppr)
                    with m.Case(XIRR):
                        # report "ICP XIRR read";
                        comb += be_out.eq(Cat(r.xisr, r.cppr))
                        with m.If(self.bus.sel == 0xf): #  # 4 byte
                            comb += xirr_accept_rd.eq(1)
                    with m.Case(MFRR):
                        # report "ICP MFRR read";
                        comb += be_out.eq(r.mfrr)

        comb += pending_priority.eq(0xff)
        comb += v.xisr.eq(0x0)
        comb += v.irq.eq(0x0)

        with m.If(self.ics_i.pri != 0xff):
            comb += v.xisr.eq(Cat(self.ics_i.src, Const(0x00001)))
            comb += pending_priority.eq(self.ics_i.pri)

        # Check MFRR
        with m.If(r.mfrr < pending_priority):
            comb += v.xisr.eq(Const(0x2)) # special XICS MFRR IRQ source number
            comb += pending_priority.eq(r.mfrr)

        # Accept the interrupt
        with m.If(xirr_accept_rd):
            #report "XICS: ICP ACCEPT" &
            #    " cppr:" &  to_hstring(r.cppr) &
            #    " xisr:" & to_hstring(r.xisr) &
            #    " mfrr:" & to_hstring(r.mfrr);
            comb += v.cppr.eq(pending_priority)

        comb += v.wb_rd_data.eq(bswap(be_out))

        pp_ok = Signal()
        comb += pp_ok.eq(pending_priority < v.cppr)
        with m.If(pp_ok):
            with m.If(~r.irq):
                #report "IRQ set";
                pass
            comb += v.irq.eq(1)
        with m.Elif(r.irq):
            #report "IRQ clr";
            pass

        comb += r_next.eq(v)

        return m

    def __iter__(self):
        for field in self.bus.fields.values():
            yield field
        yield from self.ics_i
        yield self.core_irq_o

    def ports(self):
        return list(self)


class Xive(RecordObject):
    def __init__(self, name, wid, rst):
        super().__init__(name=name)
        self.pri = Signal(wid, reset=rst)



class XICS_ICS(Elaboratable):
    def __init__(self, SRC_NUM=16, PRIO_BITS=8):
        self.SRC_NUM = SRC_NUM
        self.PRIO_BITS = PRIO_BITS
        self.pri_masked = (1<<self.PRIO_BITS)-1
        class Spec: pass
        spec = Spec()
        spec.addr_wid = 30
        spec.mask_wid = 4
        spec.reg_wid = 32
        self.bus = Record(make_wb_layout(spec))

        self.int_level_i = Signal(SRC_NUM)
        self.icp_out = ICS2ICP("icp_o")

    def prio_pack(self, pri8):
        return pri8[:self.PRIO_BITS]

    def prio_unpack(self, pri):
        return Mux(pri == self.pri_masked, 0xff, pri[:self.PRIO_BITS])

    # A more favored than b ?
    def a_mf_b(self, a, b):
        #report "a_mf_b a=" & to_hstring(a) &
        #    " b=" & to_hstring(b) &
        #    " r=" & boolean'image(a < b);
        return a < b;

    def elaborate(self, platform):
        m = Module()
        comb, sync = m.d.comb, m.d.sync

        xives = Array([Xive("xive%d" % i, self.PRIO_BITS, self.pri_masked)
                            for i in range(self.SRC_NUM)])

        wb_valid = Signal()
        reg_idx = Signal(log2_int(self.SRC_NUM))
        icp_out_next = ICS2ICP("icp_r")
        int_level_l = Signal(self.SRC_NUM)

        # Register map
        #     0  : Config
        #     4  : Debug/diagnostics
        #   800  : XIVE0
        #   804  : XIVE1 ...
        #
        # Config register format:
        #
        #  23..  0 : Interrupt base (hard wired to 16)
        #  27.. 24 : #prio bits (1..8)
        #
        # XIVE register format:
        #
        #       31 : input bit (reflects interrupt input)
        #       30 : reserved
        #       29 : P (mirrors input for now)
        #       28 : Q (not implemented in this version)
        # 30 ..    : reserved
        # 19 ..  8 : target (not implemented in this version)
        #  7 ..  0 : prio/mask

        reg_is_xive  = Signal()
        reg_is_config = Signal()
        reg_is_debug  = Signal()

        assert self.SRC_NUM == 16, "Fixup address decode with log2"

        comb += reg_is_xive.eq(self.bus.adr[11])
        comb += reg_is_config.eq(self.bus.adr[0:12] == 0x0)
        comb += reg_is_debug.eq(self.bus.adr[0:12] == 0x4)

        # Register index XX FIXME: figure out bits from SRC_NUM
        comb += reg_idx.eq(self.bus.adr[2:6])

        # Latch interrupt inputs for timing
        sync += int_level_l.eq(self.int_level_i)

        # We don't stall. Acks are sent by the read machine one cycle
        # after a request, but we can handle one access per cycle.
        comb += wb_valid.eq(self.bus.cyc & self.bus.stb)

        # Big read mux. This could be replaced by a slower state
        # machine iterating registers instead if timing gets tight.
        be_out = Signal(32)
        comb += be_out.eq(0)

        # XIVE reg
        with m.If(reg_is_xive):
            pri_i = self.prio_unpack(xives[reg_idx].pri)
            ibit = Signal()
            comb += ibit.eq(int_level_l.bit_select(reg_idx, 1))
            comb += be_out.eq(Cat(pri_i,         # bits 0..7
                                  Const(0, 20),  # 8-27
                                  0,             # 28
                                  ibit,          # 29
                                  0,             # 30
                                  ibit))         # 31
        # Config reg
        with m.Elif(reg_is_config):
            comb += be_out.eq(Cat(Const(self.SRC_NUM, 24),  # 0-23
                                  Const(self.PRIO_BITS, 4), # 24-27
                                  Const(0, 4)))             # 28-31
        # Debug reg
        with m.Elif(reg_is_debug):
            comb += be_out.eq(Cat(icp_out_next.pri,  # 0-7
                                  Const(0, 20),      # 8-27
                                  icp_out_next.src)) # 28-31

        sync += self.bus.dat_r.eq(bswap(be_out))
        sync += self.bus.ack.eq(wb_valid)

        # Register write machine
        be_in  = Signal(32)
        # Byteswapped input
        comb += be_in.eq(bswap(self.bus.dat_w))

        with m.If(wb_valid & self.bus.we):
            with m.If(reg_is_xive):
                # TODO: When adding support for other bits, make sure to
                # properly implement self.bus.sel to allow partial writes.
                sync += xives[reg_idx].pri.eq(self.prio_pack(be_in[:8]))
                #report "ICS irq " & integer'image(reg_idx) &
                #    " set to:" & to_hstring(be_in(7 downto 0));

        # generate interrupt. This is a simple combinational process,
        # potentially wasteful in HW for large number of interrupts.
        #
        # could be replaced with iterative state machines and a message
        # system between ICSs' (plural) and ICP  incl. reject etc...
        #
        sync += self.icp_out.eq(icp_out_next)

        max_idx = Signal(log2_int(self.SRC_NUM))
        max_pri = Signal(self.PRIO_BITS)

        # XXX FIXME: Use a tree
        comb += max_pri.eq(self.pri_masked)
        comb += max_idx.eq(0)
        for i in range(self.SRC_NUM):
            with m.If(int_level_l[i] & self.a_mf_b(xives[i].pri, max_pri)):
                comb += max_pri.eq(xives[i].pri)
                comb += max_idx.eq(i)
        with m.If(max_pri != self.pri_masked):
            #report "MFI: " & integer'image(max_idx) &
            #" pri=" & to_hstring(prio_unpack(max_pri));
            pass
        comb += icp_out_next.src.eq(max_idx)
        comb += icp_out_next.pri.eq(self.prio_unpack(max_pri))

        return m

    def __iter__(self):
        for field in self.bus.fields.values():
            yield field
        yield self.int_level_i
        yield from self.icp_out.ports()

    def ports(self):
        return list(self)


def wb_write(dut, addr, data, sel=True):

    # read wb
    yield dut.bus.cyc.eq(1)
    yield dut.bus.stb.eq(1)
    yield dut.bus.we.eq(1)
    yield dut.bus.sel.eq(0b1111 if sel else 0b1) # 32-bit / 8-bit
    yield dut.bus.adr.eq(addr)
    yield dut.bus.dat_w.eq(data)

    # wait for ack to go high
    while True:
        ack = yield dut.bus.ack
        print ("ack", ack)
        if ack:
            break
        yield # loop until ack

    # leave cyc/stb valid for 1 cycle while writing
    yield

    # clear out before returning data
    yield dut.bus.cyc.eq(0)
    yield dut.bus.stb.eq(0)
    yield dut.bus.we.eq(0)
    yield dut.bus.adr.eq(0)
    yield dut.bus.sel.eq(0)
    yield dut.bus.dat_w.eq(0)


def wb_read(dut, addr, sel=True):

    # read wb
    yield dut.bus.cyc.eq(1)
    yield dut.bus.stb.eq(1)
    yield dut.bus.we.eq(0)
    yield dut.bus.sel.eq(0b1111 if sel else 0b1) # 32-bit / 8-bit
    yield dut.bus.adr.eq(addr)

    # wait for ack to go high
    while True:
        ack = yield dut.bus.ack
        print ("ack", ack)
        if ack:
            break
        yield # loop until ack

    # get data on same cycle that ack raises
    data = yield dut.bus.dat_r

    # leave cyc/stb valid for 1 cycle while reading
    yield

    # clear out before returning data
    yield dut.bus.cyc.eq(0)
    yield dut.bus.stb.eq(0)
    yield dut.bus.we.eq(0)
    yield dut.bus.adr.eq(0)
    yield dut.bus.sel.eq(0)
    return data


def sim_xics_icp(dut):

    # read wb XIRR_MFRR
    data = yield from wb_read(dut, MFRR)
    print ("mfrr", hex(data), bin(data))
    assert (yield dut.core_irq_o) == 0

    yield

    # read wb XIRR (8-bit)
    data = yield from wb_read(dut, XIRR, False)
    print ("xirr", hex(data), bin(data))
    assert (yield dut.core_irq_o) == 0

    yield

    # read wb XIRR (32-bit)
    data = yield from wb_read(dut, XIRR)
    print ("xirr", hex(data), bin(data))
    assert (yield dut.core_irq_o) == 0

    yield

    # read wb XIRR_POLL
    data = yield from wb_read(dut, XIRR_POLL)
    print ("xirr poll", hex(data), bin(data))
    assert (yield dut.core_irq_o) == 0

    ##################
    # set dut src/pri to something, anything

    yield dut.ics_i.src.eq(9)
    yield dut.ics_i.pri.eq(0x1e)

    # read wb XIRR_MFRR
    data = yield from wb_read(dut, MFRR)
    print ("mfrr", hex(data), bin(data))
    assert (yield dut.core_irq_o) == 0

    yield

    # read wb XIRR (8-bit)
    data = yield from wb_read(dut, XIRR, False)
    print ("xirr", hex(data), bin(data))
    assert (yield dut.core_irq_o) == 0

    yield

    # read wb XIRR (32-bit)
    data = yield from wb_read(dut, XIRR)
    print ("xirr", hex(data), bin(data))
    assert (yield dut.core_irq_o) == 0

    yield

    # read wb XIRR_POLL
    data = yield from wb_read(dut, XIRR_POLL)
    print ("xirr poll", hex(data), bin(data))
    assert (yield dut.core_irq_o) == 0

    ######################
    # write XIRR
    data = 0xff
    yield from wb_write(dut, XIRR, data)
    print ("xirr written", hex(data), bin(data))

    yield
    assert (yield dut.core_irq_o) == 1
    yield
    yield
    yield

    # read wb XIRR_POLL
    #data = yield from wb_read(dut, XIRR_POLL, False)
    #print ("xirr poll", hex(data), bin(data))
    #assert (yield dut.core_irq_o) == 1

    yield

    # read wb XIRR (32-bit)
    data = yield from wb_read(dut, XIRR)
    print ("xirr", hex(data), bin(data))
    yield
    assert (yield dut.core_irq_o) == 0

    yield


def test_xics_icp():

    dut = XICS_ICP()
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_xics_icp.il", "w") as f:
        f.write(vl)

    m = Module()
    m.submodules.xics_icp = dut

    sim = Simulator(m)
    sim.add_clock(1e-6)

    sim.add_sync_process(wrap(sim_xics_icp(dut)))
    sim_writer = sim.write_vcd('test_xics_icp.vcd')
    with sim_writer:
        sim.run()

def test_xics_ics():

    dut = XICS_ICS()
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_xics_ics.il", "w") as f:
        f.write(vl)

    #run_simulation(dut, ldst_sim(dut), vcd_name='test_ldst_regspec.vcd')


if __name__ == '__main__':
    test_xics_icp()
    test_xics_ics()

