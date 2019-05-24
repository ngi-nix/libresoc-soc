from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Elaboratable

from nmutil.latch import SRLatch, latchregister

""" Computation Unit (aka "ALU Manager").

    This module runs a "revolving door" set of three latches, based on
    * Issue
    * Go_Read
    * Go_Write
    where one of them cannot be set on any given cycle.
    (Note however that opc_l has been inverted (and qn used), due to SRLatch
     default reset state being "0" rather than "1")

    * When issue is first raised, a busy signal is sent out.
      The src1 and src2 registers and the operand can be latched in
      at this point

    * Read request is set, which is acknowledged through the Scoreboard
      to the priority picker, which generates (one and only one) Go_Read
      at a time.  One of those will (eventually) be this Computation Unit.

    * Once Go_Read is set, the src1/src2/operand latch door shuts (locking
      src1/src2/operand in place), and the ALU is told to proceed.

    * As this is currently a "demo" unit, a countdown timer is activated
      to simulate an ALU "pipeline", which activates "write request release",
      and the ALU's output is captured into a temporary register.

    * Write request release will go through a similar process as Read request,
      resulting (eventually) in Go_Write being asserted.

    * When Go_Write is asserted, two things happen: (1) the data in the temp
      register is placed combinatorially onto the output, and (2) the
      req_l latch is cleared, busy is dropped, and the Comp Unit is back
      through its revolving door to do another task.
"""

class ComputationUnitNoDelay(Elaboratable):
    def __init__(self, rwid, opwid, alu):
        self.rwid = rwid
        self.alu = alu

        self.counter = Signal(4)
        self.go_rd_i = Signal(reset_less=True) # go read in
        self.go_wr_i = Signal(reset_less=True) # go write in
        self.issue_i = Signal(reset_less=True) # fn issue in
        self.shadown_i = Signal(reset=1) # shadow function, defaults to ON
        self.go_die_i = Signal() # go die (reset)

        self.oper_i = Signal(opwid, reset_less=True) # opcode in
        self.src1_i = Signal(rwid, reset_less=True) # oper1 in
        self.src2_i = Signal(rwid, reset_less=True) # oper2 in

        self.busy_o = Signal(reset_less=True) # fn busy out
        self.data_o = Signal(rwid, reset_less=True) # Dest out
        self.rd_rel_o = Signal(reset_less=True) # release src1/src2 request
        self.req_rel_o = Signal(reset_less=True) # release request out (valid_o)

    def elaborate(self, platform):
        m = Module()
        m.submodules.alu = self.alu
        m.submodules.src_l = src_l = SRLatch(sync=False)
        m.submodules.opc_l = opc_l = SRLatch(sync=False)
        m.submodules.req_l = req_l = SRLatch(sync=False)

        # shadow/go_die
        reset_w = Signal(reset_less=True)
        reset_r = Signal(reset_less=True)
        m.d.comb += reset_w.eq(self.go_wr_i | self.go_die_i)
        m.d.comb += reset_r.eq(self.go_rd_i | self.go_die_i)

        # This is fascinating and very important to observe that this
        # is in effect a "3-way revolving door".  At no time may all 3
        # latches be set at the same time.

        # opcode latch (not using go_rd_i) - inverted so that busy resets to 0
        m.d.sync += opc_l.s.eq(self.issue_i) # XXX NOTE: INVERTED FROM book!
        m.d.sync += opc_l.r.eq(reset_w)      # XXX NOTE: INVERTED FROM book!

        # src operand latch (not using go_wr_i)
        m.d.sync += src_l.s.eq(self.issue_i)
        m.d.sync += src_l.r.eq(reset_r)

        # dest operand latch (not using issue_i)
        m.d.sync += req_l.s.eq(self.go_rd_i)
        m.d.sync += req_l.r.eq(reset_w)

        # XXX
        # XXX NOTE: sync on req_rel_o and data_o due to simulation lock-up
        # XXX

        # outputs
        m.d.comb += self.busy_o.eq(opc_l.q) # busy out
        m.d.comb += self.rd_rel_o.eq(src_l.q & opc_l.q) # src1/src2 req rel

        # the counter is just for demo purposes, to get the ALUs of different
        # types to take arbitrary completion times
        with m.If(opc_l.qn):
            m.d.sync += self.counter.eq(0)
        with m.If(req_l.qn & opc_l.q & (self.counter == 0)):
            with m.If(self.oper_i == 2): # MUL, to take 5 instructions
                m.d.sync += self.counter.eq(5)
            with m.Elif(self.oper_i == 3): # SHIFT to take 7
                m.d.sync += self.counter.eq(7)
            with m.Else(): # ADD/SUB to take 2
                m.d.sync += self.counter.eq(2)
        with m.If(self.counter > 1):
            m.d.sync += self.counter.eq(self.counter - 1)
        with m.If(self.counter == 1):
            # write req release out.  waits until shadow is dropped.
            m.d.comb += self.req_rel_o.eq(req_l.q & opc_l.q & self.shadown_i)

        # create a latch/register for src1/src2
        latchregister(m, self.src1_i, self.alu.a, src_l.q)
        latchregister(m, self.src2_i, self.alu.b, src_l.q)
        #with m.If(src_l.qn):
        #    m.d.comb += self.alu.op.eq(self.oper_i)

        # create a latch/register for the operand
        latchregister(m, self.oper_i, self.alu.op, src_l.q)

        # and one for the output from the ALU
        data_r = Signal(self.rwid, reset_less=True) # Dest register
        latchregister(m, self.alu.o, data_r, req_l.q)

        with m.If(self.go_wr_i):
            m.d.comb += self.data_o.eq(data_r)

        return m

def scoreboard_sim(dut):
    yield dut.dest_i.eq(1)
    yield dut.issue_i.eq(1)
    yield
    yield dut.issue_i.eq(0)
    yield
    yield dut.src1_i.eq(1)
    yield dut.issue_i.eq(1)
    yield
    yield
    yield
    yield dut.issue_i.eq(0)
    yield
    yield dut.go_read_i.eq(1)
    yield
    yield dut.go_read_i.eq(0)
    yield
    yield dut.go_write_i.eq(1)
    yield
    yield dut.go_write_i.eq(0)
    yield

def test_scoreboard():
    dut = Scoreboard(32, 8)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_scoreboard.il", "w") as f:
        f.write(vl)

    run_simulation(dut, scoreboard_sim(dut), vcd_name='test_scoreboard.vcd')

if __name__ == '__main__':
    test_scoreboard()
