from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Mux, Elaboratable

from nmutil.latch import SRLatch, latchregister
from openpower.decoder.power_decoder2 import Data
from openpower.decoder.power_enums import MicrOp

from soc.experiment.alu_hier import CompALUOpSubset

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
    def __init__(self, rwid, alu):
        self.rwid = rwid
        self.alu = alu  # actual ALU - set as a "submodule" of the CU

        self.counter = Signal(4)
        self.go_rd_i = Signal(reset_less=True)  # go read in
        self.go_wr_i = Signal(reset_less=True)  # go write in
        self.issue_i = Signal(reset_less=True)  # fn issue in
        self.shadown_i = Signal(reset=1)  # shadow function, defaults to ON
        self.go_die_i = Signal()  # go die (reset)

        # operation / data input
        self.oper_i = CompALUOpSubset()  # operand
        self.src1_i = Signal(rwid, reset_less=True)  # oper1 in
        self.src2_i = Signal(rwid, reset_less=True)  # oper2 in

        self.busy_o = Signal(reset_less=True)  # fn busy out
        self.data_o = Signal(rwid, reset_less=True)  # Dest out
        self.rd_rel_o = Signal(reset_less=True)  # release src1/src2 request
        # release request out (valid_o)
        self.req_rel_o = Signal(reset_less=True)
        self.done_o = self.req_rel_o  # 'normalise' API

    def elaborate(self, platform):
        m = Module()
        m.submodules.alu = self.alu
        m.submodules.src_l = src_l = SRLatch(sync=False, name="src")
        m.submodules.opc_l = opc_l = SRLatch(sync=False, name="opc")
        m.submodules.req_l = req_l = SRLatch(sync=False, name="req")

        # shadow/go_die
        reset_w = Signal(reset_less=True)
        reset_r = Signal(reset_less=True)
        m.d.comb += reset_w.eq(self.go_wr_i | self.go_die_i)
        m.d.comb += reset_r.eq(self.go_rd_i | self.go_die_i)

        # This is fascinating and very important to observe that this
        # is in effect a "3-way revolving door".  At no time may all 3
        # latches be set at the same time.

        # opcode latch (not using go_rd_i) - inverted so that busy resets to 0
        m.d.sync += opc_l.s.eq(self.issue_i)  # XXX NOTE: INVERTED FROM book!
        m.d.sync += opc_l.r.eq(reset_w)      # XXX NOTE: INVERTED FROM book!

        # src operand latch (not using go_wr_i)
        m.d.sync += src_l.s.eq(self.issue_i)
        m.d.sync += src_l.r.eq(reset_r)

        # dest operand latch (not using issue_i)
        m.d.sync += req_l.s.eq(self.go_rd_i)
        m.d.sync += req_l.r.eq(reset_w)

        # create a latch/register for the operand
        oper_r = CompALUOpSubset()
        latchregister(m, self.oper_i, oper_r, self.issue_i, "oper_l")

        # and one for the output from the ALU
        data_r = Signal(self.rwid, reset_less=True)  # Dest register
        latchregister(m, self.alu.o, data_r, req_l.q, "data_l")

        # pass the operation to the ALU
        m.d.comb += self.alu.op.eq(oper_r)

        # select immediate if opcode says so.  however also change the latch
        # to trigger *from* the opcode latch instead.
        op_is_imm = oper_r.imm_data.imm_ok
        src2_or_imm = Signal(self.rwid, reset_less=True)
        src_sel = Signal(reset_less=True)
        m.d.comb += src_sel.eq(Mux(op_is_imm, opc_l.q, src_l.q))
        m.d.comb += src2_or_imm.eq(Mux(op_is_imm, oper_r.imm_data.imm,
                                       self.src2_i))

        # create a latch/register for src1/src2
        latchregister(m, self.src1_i, self.alu.a, src_l.q)
        latchregister(m, src2_or_imm, self.alu.b, src_sel)

        # -----
        # outputs
        # -----

        # all request signals gated by busy_o.  prevents picker problems
        busy_o = self.busy_o
        m.d.comb += busy_o.eq(opc_l.q)  # busy out
        m.d.comb += self.rd_rel_o.eq(src_l.q & busy_o)  # src1/src2 req rel

        # on a go_read, tell the ALU we're accepting data.
        # NOTE: this spells TROUBLE if the ALU isn't ready!
        # go_read is only valid for one clock!
        with m.If(self.go_rd_i):                     # src operands ready, GO!
            with m.If(~self.alu.p_ready_o):          # no ACK yet
                m.d.comb += self.alu.p_valid_i.eq(1)  # so indicate valid

        # only proceed if ALU says its output is valid
        with m.If(self.alu.n_valid_o):
            # when ALU ready, write req release out. waits for shadow
            m.d.comb += self.req_rel_o.eq(req_l.q & busy_o & self.shadown_i)
            # when output latch is ready, and ALU says ready, accept ALU output
            with m.If(self.req_rel_o & self.go_wr_i):
                # tells ALU "thanks got it"
                m.d.comb += self.alu.n_ready_i.eq(1)

        # output the data from the latch on go_write
        with m.If(self.go_wr_i):
            m.d.comb += self.data_o.eq(data_r)

        return m

    def __iter__(self):
        yield self.go_rd_i
        yield self.go_wr_i
        yield self.issue_i
        yield self.shadown_i
        yield self.go_die_i
        yield from self.oper_i.ports()
        yield self.src1_i
        yield self.src2_i
        yield self.busy_o
        yield self.rd_rel_o
        yield self.req_rel_o
        yield self.data_o

    def ports(self):
        return list(self)


def op_sim(dut, a, b, op, inv_a=0, imm=0, imm_ok=0):
    yield dut.issue_i.eq(0)
    yield
    yield dut.src1_i.eq(a)
    yield dut.src2_i.eq(b)
    yield dut.oper_i.insn_type.eq(op)
    yield dut.oper_i.invert_in.eq(inv_a)
    yield dut.oper_i.imm_data.imm.eq(imm)
    yield dut.oper_i.imm_data.imm_ok.eq(imm_ok)
    yield dut.issue_i.eq(1)
    yield
    yield dut.issue_i.eq(0)
    yield
    yield dut.go_rd_i.eq(1)
    while True:
        yield
        rd_rel_o = yield dut.rd_rel_o
        print("rd_rel", rd_rel_o)
        if rd_rel_o:
            break
    yield
    yield dut.go_rd_i.eq(0)
    req_rel_o = yield dut.req_rel_o
    result = yield dut.data_o
    print("req_rel", req_rel_o, result)
    while True:
        req_rel_o = yield dut.req_rel_o
        result = yield dut.data_o
        print("req_rel", req_rel_o, result)
        if req_rel_o:
            break
        yield
    yield dut.go_wr_i.eq(1)
    yield
    result = yield dut.data_o
    print("result", result)
    yield dut.go_wr_i.eq(0)
    yield
    return result


def scoreboard_sim(dut):
    result = yield from op_sim(dut, 5, 2, MicrOp.OP_ADD, inv_a=0,
                               imm=8, imm_ok=1)
    assert result == 13

    result = yield from op_sim(dut, 5, 2, MicrOp.OP_ADD, inv_a=1)
    assert result == 65532

    result = yield from op_sim(dut, 5, 2, MicrOp.OP_ADD)
    assert result == 7


def test_scoreboard():
    from alu_hier import ALU
    from openpower.decoder.power_decoder2 import Decode2ToExecute1Type

    alu = ALU(16)
    dut = ComputationUnitNoDelay(16, alu)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_compalu.il", "w") as f:
        f.write(vl)

    run_simulation(dut, scoreboard_sim(dut), vcd_name='test_compalu.vcd')


if __name__ == '__main__':
    test_scoreboard()
