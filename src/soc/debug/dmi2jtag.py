"""JTAGToDMI

based on Anton Blanchard microwatt dmi_dtm_xilinx.vhdl

"""

from enum import Enum, unique
from nmigen import (Module, Signal, Elaboratable, Cat, Signal)
from nmigen.cli import main
from nmigen.cli import rtlil
from nmutil.iocontrol import RecordObject
from nmutil.byterev import byte_reverse
from nmutil.mask import Mask
from nmigen.util import log2_int

# -- Xilinx internal JTAG to DMI interface
# --
# -- DMI bus
# --
# --  req : ____/------------\_____
# --  addr: xxxx<            >xxxxx
# --  dout: xxxx<            >xxxxx
# --  wr  : xxxx<            >xxxxx
# --  din : xxxxxxxxxxxx<      >xxx
# --  ack : ____________/------\___
# --
# --  * addr/dout set along with req, can be latched on same cycle by slave
# --  * ack & din remain up until req is dropped by master, the slave must
# --    provide a stable output on din on reads during that time.
# --  * req remains low at until at least one sysclk after ack seen down.
# --
# --   JTAG (tck)                    DMI (sys_clk)
# --
# --   * jtag_req = 1
# --        (jtag_req_0)             *
# --          (jtag_req_1) ->        * dmi_req = 1 >
# --                                 *.../...
# --                                 * dmi_ack = 1 <
# --   *                         (dmi_ack_0)
# --   *                   <-  (dmi_ack_1)
# --   * jtag_req = 0 (and latch dmi_din)
# --        (jtag_req_0)             *
# --          (jtag_req_1) ->        * dmi_req = 0 >
# --                                 * dmi_ack = 0 <
# --  *                          (dmi_ack_0)
# --  *                    <-  (dmi_ack_1)
# --
# --  jtag_req can go back to 1 when jtag_rsp_1 is 0
# --
# --  Questions/TODO:
# --    - I use 2 flip fops for sync, is that enough ?
# --    - I treat the jtag_reset as an async reset, is that necessary ?
# --    - Dbl check reset situation since we have two different resets
# --      each only resetting part of the logic...
# --    - Look at optionally removing the synchronizer on the ack path,
# --      assuming JTAG is always slow enough that ack will have been
# --      stable long enough by the time CAPTURE comes in.
# --    - We could avoid the latched request by not shifting while a
# --      request is in progress (and force TDO to 1 to return a busy
# --      status).
# --
# --  WARNING: This isn't the real DMI JTAG protocol (at least not yet).
# --           a command while busy will be ignored. A response of "11"
# --           means the previous command is still going, try again.
# --           As such We don't implement the DMI "error" status, and
# --           we don't implement DTMCS yet... This may still all change
# --           but for now it's easier that way as the real DMI protocol
# --           requires for a command to work properly that enough TCK
# --           are sent while IDLE and I'm having trouble getting that
# --           working with UrJtag and the Xilinx BSCAN2 for now.


# ** Constants **
DMI_REQ_NOP = Const(0b00, 2)
DMI_REQ_RD  = Const(0b01, 2)
DMI_REQ_WR  = Const(0b10, 2)
DMI_RSP_OK  = Const(0b00, 2)
DMI_RSP_BSY = Const(0b11, 2)


class JTAGToDMI(Elaboratable):
    def __init__(self, ABITS=8, DBITS=32):
        self.ABITS = ABITS
        self.DBITS = DBITS
        self.sys_clk   = Signal()
        self.sys_reset = Signal()
        self.dmi_addr  = Signal(ABITS)
        self.dmi_din   = Signal(DBITS)
        self.dmi_dout  = Signal(DBITS)
        self.dmi_req   = Signal()
        self.dmi_wr    = Signal()
        self.dmi_ack   = Signal()
        self.dmi_err   = Signal()

    # DMI req synchronization
    def dmi_req_sync(self, m, jtag_req):

        # Syncrhonizer for jtag_req (jtag clk -> sys clk)
        jtag_req_0 = Signal()
        jtag_req_1 = Signal()

        sync = m.d.SYS_sync

        with m.If(sys_reset):
            sync += jtag_req_0.eq(0)
            sync += jtag_req_1.eq(0)

        with m.Else():
            sync += jtag_req_0.eq(jtag_req)
            sync += jtag_req_1.eq(jtag_req_0)
        comb += self.dmi_req.eq(jtag_req_1)

    # DMI ack synchronization
    def dmi_ack_sync(self, m, dmi_ack_1):
        comb = m.d.comb
        sync = m.d.JTAG_sync

        dmi_ack_0 = Signal()

        # 	-- jtag_reset is async (see comments)
        with m.If(jtag_reset):
            comb += dmi_ack_0.eq(0)
            comb += dmi_ack_1.eq(0)

        sync += dmi_ack_0.eq(self.dmi_ack)
        sync += dmi_ack_1.eq(dmi_ack_0)

    def elaborate(self, platform):
        m = Module()

        comb = m.d.comb
        sync = m.d.sync

        # Signal coming out of the BSCANE2 block
        jtag_reset = Signal()
        capture    = Signal()
        update     = Signal()
        drck       = Signal()
        jtag_clk   = Signal()
        sel        = Signal()
        shift      = Signal()
        tdi        = Signal()
        tdo        = Signal()
        tck        = Signal()

        # ** JTAG clock domain **

        # Shift register
        shiftr = Signal(self.ABITS + self.DBITS)

        # Latched request
        request = Signal(ABITS + DBITS)

        dmi_ack_1 = Signal()

        # A request is present
        jtag_req = Signal()

        # ** SYS clock domain

        # combination signals
        jtag_bsy = Signal()
        op_valid = Signal()
        rsp_op   = Signal(2)

    #     attribute ASYNC_REG : string;
    #     attribute ASYNC_REG of jtag_req_0: signal is "TRUE";
    #     attribute ASYNC_REG of jtag_req_1: signal is "TRUE";
    #     attribute ASYNC_REG of dmi_ack_0: signal is "TRUE";
    #     attribute ASYNC_REG of dmi_ack_1: signal is "TRUE";
        # TODO nmigen attributes
        # attribute ASYNC_REG : string;
        # attribute ASYNC_REG of jtag_req_0: signal is "TRUE";
        # attribute ASYNC_REG of jtag_req_1: signal is "TRUE";
        # attribute ASYNC_REG of dmi_ack_0: signal is "TRUE";
        # attribute ASYNC_REG of dmi_ack_1: signal is "TRUE";


# begin
#
#     -- Implement the Xilinx bscan2 for series 7 devices (TODO: use PoC
#     -- to wrap this if compatibility is required with older devices).
#     bscan : BSCANE2
# 	generic map (
# 	    JTAG_CHAIN		=> 2
# 	    )
# 	port map (
# 	    CAPTURE		=> capture,
# 	    DRCK		=> drck,
# 	    RESET		=> jtag_reset,
# 	    RUNTEST		=> open,
# 	    SEL			=> sel,
# 	    SHIFT		=> shift,
# 	    TCK			=> tck,
# 	    TDI			=> tdi,
# 	    TMS			=> open,
# 	    UPDATE		=> update,
# 	    TDO			=> tdo
# 	    );
#
#     -- Some examples out there suggest buffering the clock so it's
#     -- treated as a proper clock net. This is probably needed when using
#     -- drck (the gated clock) but I'm using the real tck here to avoid
#     -- missing the update phase so maybe not...
#     --
#     clkbuf : BUFG
# 	port map (
# --	    I => drck,
# 	    I => tck,
# 	    O => jtag_clk
# 	    );
#
        # jtag_bsy indicates whether we can start a new request,
        # we can when we aren't already processing one (jtag_req)
        # and the synchronized ack of the previous one is 0.
        comb += jtag_bsy.eq(jtag_req | dmi_ack_1)

        #     -- decode request type in shift register
        with m.Switch(shitr[:2]):
            with m.Case(DMI_REQ_RD): comb += op_valid.eq(1)
            with m.Case(DMI_REQ_WR): comb += op_valid.eq(1)

        #     -- encode response op
        with m.If(jtag_bsy):
            comb += rsp_op.eq(DMI_RSP_BSY)
        with m.Else():
            comb += rsp_op.eq(DMI_RSP_OK)

        # Some DMI out signals are directly driven from the request register
        # dmi_addr <= request(ABITS + DBITS + 1 downto DBITS + 2);
        # dmi_dout <= request(DBITS + 1 downto 2);
        # dmi_wr   <= '1' when request(1 downto 0) = DMI_REQ_WR else '0';
        comb += dmi_addr.eq(request[DBITS + 2:ABITS + DBITS + 2])
        comb += dmi_dout.eq(request[2:DBITS])

        with m.If(request[:2] == DMI_REQ_WR):
            comb += dmi_wr.eq(1)

        # TDO is wired to shift register bit 0
        comb += tdo.eq(shiftr[0])

    # Main state machine. Handles shift registers, request latch and
    # jtag_req latch. Could be split into 3 processes but it's probably
    # not worthwhile.
    def shifter(self, m, jtag_clk, jtag_reset)
        comb = m.d.comb
        sync = m.d.JTAG_sync

        with m.If(jtag_reset):
            comb += shiftr.eq(0)
            comb += jtag_req.eq(0)

        # Handle jtag "commands" when sel is 1
        with m.Elif(sel):
            # Shift state, rotate the register
            with m.If(shift):
                sync += shiftr.eq(Cat(shiftr[1:ABITS + DBITS], tdi))

            # Update state (trigger)
            # Latch the request if we aren't already processing
            # one and it has a valid command opcode.
            with m.If(update & op_valid):
                with m.If(~jtag_bsy):
                    sync += request.eq(shiftr)
                    sync += jtag_req.eq(1)
                # Set the shift register "op" to "busy". This will prevent
                # us from re-starting the command on the next update if
                # the command completes before that.
                sync += shiftr[:2].eq(DMI_RSP_BSY)

            # Request completion.
            # Capture the response data for reads and clear request flag.
            # Note: We clear req (and thus dmi_req) here which
            # relies on tck ticking and sel set. This means we
            # are stuck with dmi_req up if the jtag interface stops.
            # Slaves must be resilient to this.
            with m.If(jtag_rq & dmi_ack):
                sync += jtag_req.eq(0)
                with m.If(request[:2] == DMI_REQ_RD):
                    sync += request[2:DBITS].eq(dmi_din)

            # Capture state, grab latch content with updated status
            with m.If(capture):
                sync += shiftr.eq(Cat(rsp_op, request[2:ABITS + DBITS]))

