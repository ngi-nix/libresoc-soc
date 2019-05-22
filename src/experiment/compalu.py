from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Elaboratable

from nmutil.latch import SRLatch, latchregister


class ComputationUnitNoDelay(Elaboratable):
    def __init__(self, rwid, opwid, alu):
        self.rwid = rwid
        self.alu = alu

        self.counter = Signal(4)
        self.go_rd_i = Signal(reset_less=True) # go read in
        self.go_wr_i = Signal(reset_less=True) # go write in
        self.issue_i = Signal(reset_less=True) # fn issue in

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

        # This is fascinating and very important to observe that this
        # is in effect a "3-way revolving door".  At no time may all 3
        # latches be set at the same time.

        # opcode latch (not using go_rd_i) - inverted so that busy resets to 0
        m.d.sync += opc_l.s.eq(self.issue_i) # XXX NOTE: INVERTED FROM book!
        m.d.sync += opc_l.r.eq(self.go_wr_i) # XXX NOTE: INVERTED FROM book!

        # src operand latch (not using go_wr_i)
        m.d.sync += src_l.s.eq(self.issue_i)
        m.d.sync += src_l.r.eq(self.go_rd_i)

        # dest operand latch (not using issue_i)
        m.d.sync += req_l.s.eq(self.go_rd_i)
        m.d.sync += req_l.r.eq(self.go_wr_i)

        # XXX
        # XXX NOTE: sync on req_rel_o and data_o due to simulation lock-up
        # XXX

        # outputs
        m.d.comb += self.busy_o.eq(opc_l.q) # busy out
        m.d.comb += self.rd_rel_o.eq(src_l.q & opc_l.q) # src1/src2 req rel

        with m.If(req_l.qn & opc_l.q & (self.counter == 0)):
            with m.If(self.oper_i == 2): # MUL, to take 5 instructions
                m.d.sync += self.counter.eq(5)
            with m.Elif(self.oper_i == 3): # SHIFT to take 7
                m.d.sync += self.counter.eq(7)
            with m.Else(): # ADD/SUB to take 2
                m.d.sync += self.counter.eq(2)
        with m.If(self.counter > 0):
            m.d.sync += self.counter.eq(self.counter - 1)
        with m.If((self.counter == 1) | (self.counter == 0)):
            m.d.comb += self.req_rel_o.eq(req_l.q & opc_l.q) # req release out

        # create a latch/register for src1/src2
        latchregister(m, self.src1_i, self.alu.a, src_l.q)
        latchregister(m, self.src2_i, self.alu.b, src_l.q)
        #with m.If(src_l.qn):
        #    m.d.comb += self.alu.op.eq(self.oper_i)

        # create a latch/register for the operand
        latchregister(m, self.oper_i, self.alu.op, src_l.q)

        # and one for the output from the ALU
        data_o = Signal(self.rwid, reset_less=True) # Dest register
        latchregister(m, self.alu.o, data_o, req_l.q)

        with m.If(self.go_wr_i):
            m.d.comb += self.data_o.eq(data_o)

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
