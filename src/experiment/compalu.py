from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Elaboratable

from nmutil.latch import SRLatch


class ComputationUnitNoDelay(Elaboratable):
    def __init__(self, rwid, opwid, alu):
        self.rwid = rwid
        self.alu = alu

        self.go_rd_i = Signal(reset_less=True) # go read in
        self.go_wr_i = Signal(reset_less=True) # go write in
        self.issue_i = Signal(reset_less=True) # fn issue in

        self.oper_i = Signal(opwid, reset_less=True) # opcode in
        self.src1_i = Signal(rwid, reset_less=True) # oper1 in
        self.src2_i = Signal(rwid, reset_less=True) # oper2 in

        self.busy_o = Signal(reset_less=True) # fn busy out
        self.data_o = Signal(rwid, reset_less=True) # Dest out
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

        # opcode latch (not using go_rd_i)
        m.d.comb += opc_l.s.eq(self.go_wr_i)
        m.d.comb += opc_l.r.eq(self.issue_i)

        # src operand latch (not using go_wr_i)
        m.d.comb += src_l.s.eq(self.issue_i)
        m.d.comb += src_l.r.eq(self.go_rd_i)

        # dest operand latch (not using issue_i)
        m.d.comb += req_l.s.eq(self.go_rd_i)
        m.d.comb += req_l.r.eq(self.go_wr_i)

        # XXX
        # XXX NOTE: sync on req_rel_o and data_o due to simulation lock-up
        # XXX

        # outputs
        m.d.comb += self.busy_o.eq(opc_l.qn) # busy out
        m.d.comb += self.req_rel_o.eq(req_l.qn & opc_l.q) # request release out

        with m.If(src_l.q):
            m.d.comb += self.alu.a.eq(self.src1_i)
            m.d.comb += self.alu.b.eq(self.src2_i)

        with m.If(opc_l.q):
            m.d.comb += self.alu.op.eq(self.oper_i)

        with m.If(req_l.qn):
            m.d.comb += self.data_o.eq(self.alu.o)

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
