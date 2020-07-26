"""Microwatt xics.vhdl converted to nmigen
--
# This is a simple XICS compliant interrupt controller.  This is a
# Presenter (ICP) and Source (ICS) in two small units directly
# connected to each other with no routing layer.
--
# The sources have a configurable IRQ priority set a set of ICS
# registers in the source units.
--
# The source ids start at 16 for int_level_in(0) and go up from
# there (ie int_level_in(1) is source id 17). XXX Make a generic
--
# The presentation layer will pick an interupt that is more
# favourable than the current CPPR and present it via the XISR and
# send an interrpt to the processor (via e_out). This may not be the
# highest priority interrupt currently presented (which is allowed
# via XICS)
--
"""
from nmigen import Elaboratable, Module, Signal, Cat, Const, Record
from nmutil.iocontrol import RecordObject
from nmigen.cli import rtlil
from soc.minerva.wishbone import make_wb_layout


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

        comb += self.bus.dat_w.eq(r.wb_rd_data)
        comb += self.bus.ack.eq(r.wb_ack)

        v = RegInternal()
        xirr_accept_rd = Signal()

        be_in  = Signal(32)
        be_out = Signal(32)

        pending_priority = Signal(8)

        comb += v.eq(r)
        comb += v.wb_ack.eq(0)

        comb += xirr_accept_rd.eq(0)

        comb += be_in.eq(bswap(self.bus.dat_r))
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
                            #           to_hstring(wb_in.sel);
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
                            #                to_hstring(wb_in.sel);
                            pass

            with m.Else(): # read

                with m.Switch( self.bus.adr[:8]):
                    with m.Case(XIRR_POLL):
                        # report "ICP XIRR_POLL read";
                        comb += be_out.eq(r.xisr & r.cppr )
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
            # special XICS MFRR IRQ source number
            comb += v.xisr.eq(Const(0x000002))
            comb += pending_priority.eq(r.mfrr)

        # Accept the interrupt
        with m.If(xirr_accept_rd):
            #report "XICS: ICP ACCEPT" &
            #    " cppr:" &  to_hstring(r.cppr) &
            #    " xisr:" & to_hstring(r.xisr) &
            #    " mfrr:" & to_hstring(r.mfrr);
            comb += v.cppr.eq(pending_priority)

        comb += v.wb_rd_data.eq(bswap(be_out))

        with m.If(pending_priority < v.cppr):
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


"""
end architecture behaviour;

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

library work;
use work.common.all;
use work.wishbone_types.all;

entity xics_ics is
    generic (
        SRC_NUM    : integer range 1 to 256  := 16;
        PRIO_BITS  : integer range 1 to 8    := 8
        );
    port (
        clk          : in std_logic;
        rst          : in std_logic;

        wb_in        : in wb_io_master_out;
        wb_out       : out wb_io_slave_out;

        int_level_in : in std_ulogic_vector(SRC_NUM - 1 downto 0);
        icp_out      : out ics_to_icp_t
        );
end xics_ics;

architecture rtl of xics_ics is

    subtype pri_t is std_ulogic_vector(PRIO_BITS-1 downto 0);
    type xive_t is record
        pri : pri_t;
    end record;
    constant pri_masked : pri_t := (others => '1');

    type xive_array_t is array(0 to SRC_NUM-1) of xive_t;
    signal xives : xive_array_t;

    signal wb_valid : std_ulogic;
    signal reg_idx : integer range 0 to SRC_NUM - 1;
    signal icp_out_next : ics_to_icp_t;
    signal int_level_l : std_ulogic_vector(SRC_NUM - 1 downto 0);

    function bswap(v : in std_ulogic_vector(31 downto 0)) return std_ulogic_vector is
        variable r : std_ulogic_vector(31 downto 0);
    begin
        r( 7 downto  0) := v(31 downto 24);
        r(15 downto  8) := v(23 downto 16);
        r(23 downto 16) := v(15 downto  8);
        r(31 downto 24) := v( 7 downto  0);
        return r;
    end function;

    function get_config return std_ulogic_vector is
        variable r: std_ulogic_vector(31 downto 0);
    begin
        r := (others => '0');
        r(23 downto  0) := std_ulogic_vector(to_unsigned(SRC_NUM, 24));
        r(27 downto 24) := std_ulogic_vector(to_unsigned(PRIO_BITS, 4));
        return r;
    end function;

    function prio_pack(pri8: std_ulogic_vector(7 downto 0)) return pri_t is
    begin
        return pri8(PRIO_BITS-1 downto 0);
    end function;

    function prio_unpack(pri: pri_t) return std_ulogic_vector is
        variable r : std_ulogic_vector(7 downto 0);
    begin
        if pri = pri_masked then
            r := x"ff";
        else
            r := (others => '0');
            r(PRIO_BITS-1 downto 0) := pri;
        end if;
        return r;
   end function;


# Register map
    #     0  : Config
    #     4  : Debug/diagnostics
    #   800  : XIVE0
    #   804  : XIVE1 ...
    --
    # Config register format:
    --
    #  23..  0 : Interrupt base (hard wired to 16)
    #  27.. 24 : #prio bits (1..8)
    --
    # XIVE register format:
    --
    #       31 : input bit (reflects interrupt input)
    #       30 : reserved
    #       29 : P (mirrors input for now)
    #       28 : Q (not implemented in this version)
    # 30 ..    : reserved
    # 19 ..  8 : target (not implemented in this version)
    #  7 ..  0 : prio/mask

    signal reg_is_xive   : std_ulogic;
    signal reg_is_config : std_ulogic;
    signal reg_is_debug  : std_ulogic;

begin

    assert SRC_NUM = 16 report "Fixup address decode with log2";

    reg_is_xive   <= wb_in.adr(11);
    reg_is_config <= '1' when wb_in.adr(11 downto 0) = x"000" else '0';
    reg_is_debug  <= '1' when wb_in.adr(11 downto 0) = x"004" else '0';

    # Register index XX FIXME: figure out bits from SRC_NUM
    reg_idx <= to_integer(unsigned(wb_in.adr(5 downto 2)));

    # Latch interrupt inputs for timing
    int_latch: process(clk)
    begin
        if rising_edge(clk) then
            int_level_l <= int_level_in;
        end if;
    end process;

    # We don't stall. Acks are sent by the read machine one cycle
    # after a request, but we can handle one access per cycle.
    wb_out.stall <= '0';
    wb_valid <= wb_in.cyc and wb_in.stb;

    # Big read mux. This could be replaced by a slower state
    # machine iterating registers instead if timing gets tight.
    reg_read: process(clk)
        variable be_out : std_ulogic_vector(31 downto 0);
    begin
        if rising_edge(clk) then
            be_out := (others => '0');

            if reg_is_xive = '1' then
                be_out := int_level_l(reg_idx) &
                          '0' &
                          int_level_l(reg_idx) &
                          '0' &
                          x"00000" &
                          prio_unpack(xives(reg_idx).pri);
            elsif reg_is_config = '1' then
                be_out := get_config;
            elsif reg_is_debug = '1' then
                be_out := x"00000" & icp_out_next.src & icp_out_next.pri;
            end if;
            wb_out.dat <= bswap(be_out);
            wb_out.ack <= wb_valid;
        end if;
    end process;

    # Register write machine
    reg_write: process(clk)
        variable be_in  : std_ulogic_vector(31 downto 0);
    begin
        # Byteswapped input
        be_in := bswap(wb_in.dat);

        if rising_edge(clk) then
            if rst = '1' then
                for i in 0 to SRC_NUM - 1 loop
                    xives(i) <= (pri => pri_masked);
                end loop;
            elsif wb_valid = '1' and wb_in.we = '1' then
                if reg_is_xive then
                    # TODO: When adding support for other bits, make sure to
                    # properly implement wb_in.sel to allow partial writes.
                    xives(reg_idx).pri <= prio_pack(be_in(7 downto 0));
                    report "ICS irq " & integer'image(reg_idx) &
                        " set to:" & to_hstring(be_in(7 downto 0));
                end if;
            end if;
        end if;
    end process;

    # generate interrupt. This is a simple combinational process,
    # potentially wasteful in HW for large number of interrupts.
    --
    # could be replaced with iterative state machines and a message
    # system between ICSs' (plural) and ICP  incl. reject etc...
    --
    irq_gen_sync: process(clk)
    begin
        if rising_edge(clk) then
            icp_out <= icp_out_next;
        end if;
    end process;

    irq_gen: process(all)
        variable max_idx : integer range 0 to SRC_NUM-1;
        variable max_pri : pri_t;

        # A more favored than b ?
        function a_mf_b(a: pri_t; b: pri_t) return boolean is
            variable a_i : unsigned(PRIO_BITS-1 downto 0);
            variable b_i : unsigned(PRIO_BITS-1 downto 0);
        begin
            a_i := unsigned(a);
            b_i := unsigned(b);
            report "a_mf_b a=" & to_hstring(a) &
                " b=" & to_hstring(b) &
                " r=" & boolean'image(a < b);
            return a_i < b_i;
        end function;
    begin
        # XXX FIXME: Use a tree
        max_pri := pri_masked;
        max_idx := 0;
        for i in 0 to SRC_NUM - 1 loop
            if int_level_l(i) = '1' and a_mf_b(xives(i).pri, max_pri) then
                max_pri := xives(i).pri;
                max_idx := i;
            end if;
        end loop;
        if max_pri /= pri_masked then
            report "MFI: " & integer'image(max_idx) & " pri=" & to_hstring(prio_unpack(max_pri));
        end if;
        icp_out_next.src <= std_ulogic_vector(to_unsigned(max_idx, 4));
        icp_out_next.pri <= prio_unpack(max_pri);
    end process;

end architecture rtl;
"""

def test_xics_icp():

    dut = XICS_ICP()
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_xics_icp.il", "w") as f:
        f.write(vl)

    #run_simulation(dut, ldst_sim(dut), vcd_name='test_ldst_regspec.vcd')


if __name__ == '__main__':
    test_xics_icp()

