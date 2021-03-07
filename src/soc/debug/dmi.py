"""Converted from microwatt core_debug.vhdl to nmigen

Provides a DMI (Debug Module Interface) for accessing a Libre-SOC core,
compatible with microwatt's same interface.

See constants below for addresses and register formats
"""

from nmigen import Elaboratable, Module, Signal, Cat, Const, Record, Array, Mux
from nmutil.iocontrol import RecordObject
from nmigen.utils import log2_int
from nmigen.cli import rtlil
from soc.config.state import CoreState


# DMI register addresses
class DBGCore:
    CTRL         = 0b0000
    STAT         = 0b0001
    NIA          = 0b0010 # NIA register (read only for now)
    MSR          = 0b0011 # MSR (read only)
    GSPR_IDX     = 0b0100 # GSPR register index
    GSPR_DATA    = 0b0101 # GSPR register data
    LOG_ADDR     = 0b0110 # Log buffer address register
    LOG_DATA     = 0b0111 # Log buffer data register
    CR           = 0b1000 # CR (read only)
    XER          = 0b1001 # XER (read only) - note this is a TEMPORARY hack
    SVSTATE      = 0b1010 # SVSTATE register (read only for now)


# CTRL register (direct actions, write 1 to act, read back 0)
# bit     0 : Core stop
# bit     1 : Core reset (doesn't clear stop)
# bit     2 : Icache reset
# bit     3 : Single step
# bit     4 : Core start
class DBGCtrl:
    STOP    = 0
    RESET   = 1
    ICRESET = 2
    STEP    = 3
    START   = 4


# STAT register (read only)
# bit    0 : Core stopping (wait til bit 1 set)
# bit    1 : Core stopped
# bit    2 : Core terminated (clears with start or reset)
class DBGStat:
    STOPPING  = 0
    STOPPED   = 1
    TERM      = 2


class DMIInterface(RecordObject):
    def __init__(self, name=None):
        super().__init__(name=name)
        self.addr_i = Signal(4)   # DMI register address
        self.din    = Signal(64)  # DMI data write in (if we=1)
        self.dout   = Signal(64)  # DMI data read out (if we=0)
        self.req_i  = Signal()    # DMI request valid (stb)
        self.we_i   = Signal()    # DMI write-enable
        self.ack_o  = Signal()    # DMI ack request

    def connect_to(self, other):
        return [self.addr_i.eq(other.addr_i),
                self.req_i.eq(other.req_i),
                self.we_i.eq(other.we_i),
                self.din.eq(other.din),
                other.ack_o.eq(self.ack_o),
                other.dout.eq(self.dout),
                ]

class DbgReg(RecordObject):
    def __init__(self, name):
        super().__init__(name=name)
        self.req     = Signal()
        self.ack     = Signal()
        self.addr    = Signal(7) #  includes fast SPRs, others?
        self.data    = Signal(64)


class DbgCRReg(RecordObject):
    def __init__(self, name):
        super().__init__(name=name)
        self.req     = Signal()
        self.ack     = Signal()
        self.data    = Signal(32)


class CoreDebug(Elaboratable):
    def __init__(self, LOG_LENGTH=0): # TODO - debug log 512):
        # Length of log buffer
        self.LOG_LENGTH = LOG_LENGTH
        self.dmi = DMIInterface("dmi")

        # Debug actions
        self.core_stop_o       = Signal()
        self.core_rst_o        = Signal()
        self.icache_rst_o      = Signal()

        # Core status inputs
        self.terminate_i    = Signal()
        self.core_stopped_i = Signal()
        self.state = CoreState("core_dbg")

        # GSPR register read port
        self.d_gpr = DbgReg("d_gpr")

        # CR register read port
        self.d_cr = DbgReg("d_cr")

        # XER register read port
        self.d_xer = DbgReg("d_xer")

        # Core logging data
        self.log_data_i        = Signal(256)
        self.log_read_addr_i   = Signal(32)
        self.log_read_data_o   = Signal(64)
        self.log_write_addr_o  = Signal(32)

        # Misc
        self.terminated_o  = Signal()

    def elaborate(self, platform):

        m = Module()
        comb, sync = m.d.comb, m.d.sync
        dmi, d_gpr, d_cr, d_xer, = self.dmi, self.d_gpr, self.d_cr, self.d_xer

        # DMI needs fixing... make a one clock pulse
        dmi_req_i_1 = Signal()

        # Some internal wires
        stat_reg = Signal(64)

        # Some internal latches
        stopping     = Signal()
        do_step      = Signal()
        do_reset     = Signal()
        do_icreset   = Signal()
        terminated   = Signal()
        do_gspr_rd   = Signal()
        gspr_index   = Signal.like(d_gpr.addr)

        log_dmi_addr = Signal(32)
        log_dmi_data = Signal(64)
        do_dmi_log_rd = Signal()
        dmi_read_log_data = Signal()
        dmi_read_log_data_1 = Signal()

        LOG_INDEX_BITS = log2_int(self.LOG_LENGTH)

        # Single cycle register accesses on DMI except for GSPR data
        with m.Switch(dmi.addr_i):
            with m.Case(DBGCore.GSPR_DATA):
                comb += dmi.ack_o.eq(d_gpr.ack)
                comb += d_gpr.req.eq(dmi.req_i)
            with m.Case(DBGCore.CR):
                comb += dmi.ack_o.eq(d_cr.ack)
                comb += d_cr.req.eq(dmi.req_i)
            with m.Case(DBGCore.XER):
                comb += dmi.ack_o.eq(d_xer.ack)
                comb += d_xer.req.eq(dmi.req_i)
            with m.Default():
                comb += dmi.ack_o.eq(dmi.req_i)

        # Status register read composition (DBUG_CORE_STAT_xxx)
        comb += stat_reg.eq(Cat(stopping,            # bit 0
                                self.core_stopped_i, # bit 1
                                terminated))         # bit 2

        # DMI read data mux
        with m.Switch(dmi.addr_i):
            with m.Case( DBGCore.STAT):
                comb += dmi.dout.eq(stat_reg)
            with m.Case( DBGCore.NIA):
                comb += dmi.dout.eq(self.state.pc)
            with m.Case( DBGCore.MSR):
                comb += dmi.dout.eq(self.state.msr)
            with m.Case( DBGCore.SVSTATE):
                comb += dmi.dout.eq(self.state.svstate)
            with m.Case( DBGCore.GSPR_DATA):
                comb += dmi.dout.eq(d_gpr.data)
            with m.Case( DBGCore.LOG_ADDR):
                comb += dmi.dout.eq(Cat(log_dmi_addr, self.log_write_addr_o))
            with m.Case( DBGCore.LOG_DATA):
                comb += dmi.dout.eq(log_dmi_data)
            with m.Case(DBGCore.CR):
                comb += dmi.dout.eq(d_cr.data)
            with m.Case(DBGCore.XER):
                comb += dmi.dout.eq(d_xer.data)

        # DMI writes
        # Reset the 1-cycle "do" signals
        sync += do_step.eq(0)
        sync += do_reset.eq(0)
        sync += do_icreset.eq(0)
        sync += do_dmi_log_rd.eq(0)

        # Edge detect on dmi_req_i for 1-shot pulses
        sync += dmi_req_i_1.eq(dmi.req_i)
        with m.If(dmi.req_i & ~dmi_req_i_1):
            with m.If(dmi.we_i):
                #sync += Display("DMI write to " & to_hstring(dmi_addr))

                # Control register actions

                # Core control
                with m.If(dmi.addr_i == DBGCore.CTRL):
                    with m.If(dmi.din[DBGCtrl.RESET]):
                        sync += do_reset.eq(1)
                        sync += terminated.eq(0)
                    with m.If(dmi.din[DBGCtrl.STOP]):
                        sync += stopping.eq(1)
                    with m.If(dmi.din[DBGCtrl.STEP]):
                        sync += do_step.eq(1)
                        sync += terminated.eq(0)
                    with m.If(dmi.din[DBGCtrl.ICRESET]):
                        sync += do_icreset.eq(1)
                    with m.If(dmi.din[DBGCtrl.START]):
                        sync += stopping.eq(0)
                        sync += terminated.eq(0)

                # GSPR address
                with m.Elif(dmi.addr_i == DBGCore.GSPR_IDX):
                    sync += gspr_index.eq(dmi.din)

                # Log address
                with m.Elif(dmi.addr_i == DBGCore.LOG_ADDR):
                    sync += log_dmi_addr.eq(dmi.din)
                    sync += do_dmi_log_rd.eq(1)
            with m.Else():
                # sync += Display("DMI read from " & to_string(dmi_addr))
                pass

        with m.Elif(dmi_read_log_data_1 & ~dmi_read_log_data):
            # Increment log_dmi_addr after end of read from DBGCore.LOG_DATA
            lds = log_dmi_addr[:LOG_INDEX_BITS+2]
            sync += lds.eq(lds + 1)
            sync += do_dmi_log_rd.eq(1)

        sync += dmi_read_log_data_1.eq(dmi_read_log_data)
        sync += dmi_read_log_data.eq(dmi.req_i &
                                     (dmi.addr_i == DBGCore.LOG_DATA))

        # Set core stop on terminate. We'll be stopping some time *after*
        # the offending instruction, at least until we can do back flushes
        # that preserve NIA which we can't just yet.
        with m.If(self.terminate_i):
            sync += stopping.eq(1)
            sync += terminated.eq(1)

        comb += d_gpr.addr.eq(gspr_index)

        # Core control signals generated by the debug module
        comb += self.core_stop_o.eq(stopping & ~do_step)
        comb += self.core_rst_o.eq(do_reset)
        comb += self.icache_rst_o.eq(do_icreset)
        comb += self.terminated_o.eq(terminated)

        # Logging RAM (none)

        if self.LOG_LENGTH == 0:
            self.log_read_data_o.eq(0)
            self.log_write_addr_o.eq(0x00000001)

        return m

        # TODO: debug logging
        """
        maybe_log: with m.If(LOG_LENGTH > 0 generate
            subtype log_ptr_t is unsigned(LOG_INDEX_BITS - 1 downto 0)
            type log_array_t is array(0 to LOG_LENGTH - 1) of std_ulogic_vector(255 downto 0)
            signal log_array    : log_array_t
            signal log_rd_ptr   : log_ptr_t
            signal log_wr_ptr   : log_ptr_t
            signal log_toggle   = Signal()
            signal log_wr_enable = Signal()
            signal log_rd_ptr_latched : log_ptr_t
            signal log_rd       = Signal()_vector(255 downto 0)
            signal log_dmi_reading = Signal()
            signal log_dmi_read_done = Signal()

            function select_dword(data = Signal()_vector(255 downto 0)
                                  addr = Signal()_vector(31 downto 0)) return std_ulogic_vector is
                variable firstbit : integer
            begin
                firstbit := to_integer(unsigned(addr(1 downto 0))) * 64
                return data(firstbit + 63 downto firstbit)
            end

            attribute ram_style : string
            attribute ram_style of log_array : signal is "block"
            attribute ram_decomp : string
            attribute ram_decomp of log_array : signal is "power"

        begin
            # Use MSB of read addresses to stop the logging
            log_wr_enable.eq(not (self.log_read_addr(31) or log_dmi_addr(31))

            log_ram: process(clk)
            begin
                with m.If(rising_edge(clk)):
                    with m.If(log_wr_enable = '1'):
                        log_array(to_integer(log_wr_ptr)).eq(self.log_data
                    end if
                    log_rd.eq(log_array(to_integer(log_rd_ptr_latched))
                end if
            end process


            log_buffer: process(clk)
                variable b : integer
                variable data = Signal()_vector(255 downto 0)
            begin
                with m.If(rising_edge(clk)):
                    with m.If(rst = '1'):
                        log_wr_ptr.eq((others => '0')
                        log_toggle.eq('0'
                    with m.Elif(log_wr_enable = '1'):
                        with m.If(log_wr_ptr = to_unsigned(LOG_LENGTH - 1, LOG_INDEX_BITS)):
                            log_toggle.eq(not log_toggle
                        end if
                        log_wr_ptr.eq(log_wr_ptr + 1
                    end if
                    with m.If(do_dmi_log_rd = '1'):
                        log_rd_ptr_latched.eq(unsigned(log_dmi_addr(LOG_INDEX_BITS + 1 downto 2))
                    else
                        log_rd_ptr_latched.eq(unsigned(self.log_read_addr(LOG_INDEX_BITS + 1 downto 2))
                    end if
                    with m.If(log_dmi_read_done = '1'):
                        log_dmi_data.eq(select_dword(log_rd, log_dmi_addr)
                    else
                        self.log_read_data.eq(select_dword(log_rd, self.log_read_addr)
                    end if
                    log_dmi_read_done.eq(log_dmi_reading
                    log_dmi_reading.eq(do_dmi_log_rd
                end if
            end process
            self.log_write_addr(LOG_INDEX_BITS - 1 downto 0).eq(std_ulogic_vector(log_wr_ptr)
            self.log_write_addr(LOG_INDEX_BITS).eq('1'
            self.log_write_addr(31 downto LOG_INDEX_BITS + 1).eq((others => '0')
        end generate

        """

    def __iter__(self):
        yield from self.dmi
        yield self.core_stop_o
        yield self.core_rst_o
        yield self.icache_rst_o
        yield self.terminate_i
        yield self.core_stopped_i
        yield from self.state
        yield from self.d_gpr
        yield from self.d_cr
        yield from self.d_xer
        yield self.log_data_i
        yield self.log_read_addr_i
        yield self.log_read_data_o
        yield self.log_write_addr_o
        yield self.terminated_o

    def ports(self):
        return list(self)


def test_debug():

    dut = CoreDebug()
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_core_debug.il", "w") as f:
        f.write(vl)

if __name__ == '__main__':
    test_debug()

