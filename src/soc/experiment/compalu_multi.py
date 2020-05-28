"""Computation Unit (aka "ALU Manager").

Manages a Pipeline or FSM, ensuring that the start and end time are 100%
monitored.  At no time may the ALU proceed without this module notifying
the Dependency Matrices.  At no time is a result production "abandoned".
This module blocks (indicates busy) starting from when it first receives
an opcode until it receives notification that
its result(s) have been successfully stored in the regfile(s)

Documented at http://libre-soc.org/3d_gpu/architecture/compunit
"""

from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Mux, Elaboratable, Repl, Array, Cat, Const
from nmigen.hdl.rec import (Record, DIR_FANIN, DIR_FANOUT)

from nmutil.latch import SRLatch, latchregister
from nmutil.iocontrol import RecordObject

from soc.decoder.power_decoder2 import Data
from soc.decoder.power_enums import InternalOp
from soc.fu.regspec import RegSpec, RegSpecALUAPI


def go_record(n, name):
    r = Record([('go', n, DIR_FANIN),
                ('rel', n, DIR_FANOUT)], name=name)
    r.go.reset_less = True
    r.rel.reset_less = True
    return r

# see https://libre-soc.org/3d_gpu/architecture/regfile/ section on regspecs

class CompUnitRecord(RegSpec, RecordObject):
    """CompUnitRecord

    base class for Computation Units, to provide a uniform API
    and allow "record.connect" etc. to be used, particularly when
    it comes to connecting multiple Computation Units up as a block
    (very laborious)

    LDSTCompUnitRecord should derive from this class and add the
    additional signals it requires

    :subkls:      the class (not an instance) needed to construct the opcode
    :rwid:        either an integer (specifies width of all regs) or a "regspec"

    see https://libre-soc.org/3d_gpu/architecture/regfile/ section on regspecs
    """
    def __init__(self, subkls, rwid, n_src=None, n_dst=None, name=None):
        RegSpec.__init__(self, rwid, n_src, n_dst)
        RecordObject.__init__(self, name)
        self._subkls = subkls
        n_src, n_dst = self._n_src, self._n_dst

        # create source operands
        src = []
        for i in range(n_src):
            j = i + 1 # name numbering to match src1/src2
            name = "src%d_i" % j
            rw = self._get_srcwid(i)
            sreg = Signal(rw, name=name, reset_less=True)
            setattr(self, name, sreg)
            src.append(sreg)
        self._src_i = src

        # create dest operands
        dst = []
        for i in range(n_dst):
            j = i + 1 # name numbering to match dest1/2...
            name = "dest%d_i" % j
            rw = self._get_dstwid(i)
            dreg = Signal(rw, name=name, reset_less=True)
            setattr(self, name, dreg)
            dst.append(dreg)
        self._dest = dst

        # operation / data input
        self.oper_i = subkls(name="oper_i") # operand

        # create read/write and other scoreboard signalling
        self.rd = go_record(n_src, name="rd") # read in, req out
        self.wr = go_record(n_dst, name="wr") # write in, req out
        self.issue_i = Signal(reset_less=True) # fn issue in
        self.shadown_i = Signal(reset=1) # shadow function, defaults to ON
        self.go_die_i = Signal() # go die (reset)

        # output (busy/done)
        self.busy_o = Signal(reset_less=True) # fn busy out
        self.done_o = Signal(reset_less=True)


class MultiCompUnit(RegSpecALUAPI, Elaboratable):
    def __init__(self, rwid, alu, opsubsetkls, n_src=2, n_dst=1):
        """MultiCompUnit

        * :rwid:        width of register latches (TODO: allocate per regspec)
        * :alu:         ALU (pipeline, FSM) - must conform to nmutil Pipe API
        * :opsubsetkls: subset of Decode2ExecuteType
        * :n_src:       number of src operands
        * :n_dst:       number of destination operands
        """
        RegSpecALUAPI.__init__(self, rwid, alu)
        self.opsubsetkls = opsubsetkls
        self.cu = cu = CompUnitRecord(opsubsetkls, rwid, n_src, n_dst)
        n_src, n_dst = self.n_src, self.n_dst = cu._n_src, cu._n_dst
        print ("n_src %d n_dst %d" % (self.n_src, self.n_dst))

        # convenience names for src operands
        for i in range(n_src):
            j = i + 1 # name numbering to match src1/src2
            name = "src%d_i" % j
            setattr(self, name, getattr(cu, name))

        # convenience names for dest operands
        for i in range(n_dst):
            j = i + 1 # name numbering to match dest1/2...
            name = "dest%d_i" % j
            setattr(self, name, getattr(cu, name))

        # more convenience names
        self.rd = cu.rd
        self.wr = cu.wr
        self.go_rd_i = self.rd.go # temporary naming
        self.go_wr_i = self.wr.go # temporary naming
        self.rd_rel_o = self.rd.rel # temporary naming
        self.req_rel_o = self.wr.rel # temporary naming
        self.issue_i = cu.issue_i
        self.shadown_i = cu.shadown_i
        self.go_die_i = cu.go_die_i

        # operation / data input
        self.oper_i = cu.oper_i
        self.src_i = cu._src_i

        self.busy_o = cu.busy_o
        self.dest = cu._dest
        self.data_o = self.dest[0] # Dest out
        self.done_o = cu.done_o


    def _mux_op(self, m, sl, op_is_imm, imm, i):
        # select imm if opcode says so. however also change the latch
        # to trigger *from* the opcode latch instead.
        src_or_imm = Signal(self.cu._get_srcwid(i), reset_less=True)
        src_sel = Signal(reset_less=True)
        m.d.comb += src_sel.eq(Mux(op_is_imm, self.opc_l.q, self.src_l.q[i]))
        m.d.comb += src_or_imm.eq(Mux(op_is_imm, imm, self.src_i[i]))
        # overwrite 1st src-latch with immediate-muxed stuff
        sl[i][0] = src_or_imm
        sl[i][2] = src_sel
        sl[i][3] = ~op_is_imm # change rd.rel[i] gate condition

    def elaborate(self, platform):
        m = Module()
        m.submodules.alu = self.alu
        m.submodules.src_l = src_l = SRLatch(False, self.n_src, name="src")
        m.submodules.opc_l = opc_l = SRLatch(sync=False, name="opc")
        m.submodules.req_l = req_l = SRLatch(False, self.n_dst, name="req")
        m.submodules.rst_l = rst_l = SRLatch(sync=False, name="rst")
        m.submodules.rok_l = rok_l = SRLatch(sync=False, name="rdok")
        self.opc_l, self.src_l = opc_l, src_l

        # ALU only proceeds when all src are ready.  rd_rel_o is delayed
        # so combine it with go_rd_i.  if all bits are set we're good
        all_rd = Signal(reset_less=True)
        m.d.comb += all_rd.eq(self.busy_o & rok_l.q &
                    (((~self.rd.rel) | self.rd.go).all()))

        # write_requests all done
        # req_done works because any one of the last of the writes
        # is enough, when combined with when read-phase is done (rst_l.q)
        wr_any = Signal(reset_less=True)
        req_done = Signal(reset_less=True)
        m.d.comb += self.done_o.eq(self.busy_o & ~(self.wr.rel.bool()))
        m.d.comb += wr_any.eq(self.wr.go.bool())
        m.d.comb += req_done.eq(rst_l.q & wr_any)

        # shadow/go_die
        reset = Signal(reset_less=True)
        rst_r = Signal(reset_less=True) # reset latch off
        reset_w = Signal(self.n_dst, reset_less=True)
        reset_r = Signal(self.n_src, reset_less=True)
        m.d.comb += reset.eq(req_done | self.go_die_i)
        m.d.comb += rst_r.eq(self.issue_i | self.go_die_i)
        m.d.comb += reset_w.eq(self.wr.go | Repl(self.go_die_i, self.n_dst))
        m.d.comb += reset_r.eq(self.rd.go | Repl(self.go_die_i, self.n_src))

        # read-done,wr-proceed latch
        m.d.comb += rok_l.s.eq(self.issue_i)  # set up when issue starts
        m.d.comb += rok_l.r.eq(self.alu.p.ready_o) # off when ALU acknowledges

        # wr-done, back-to-start latch
        m.d.comb += rst_l.s.eq(all_rd)     # set when read-phase is fully done
        m.d.comb += rst_l.r.eq(rst_r)        # *off* on issue

        # opcode latch (not using go_rd_i) - inverted so that busy resets to 0
        m.d.sync += opc_l.s.eq(self.issue_i)       # set on issue
        m.d.sync += opc_l.r.eq(self.alu.n.valid_o & req_done) # reset on ALU

        # src operand latch (not using go_wr_i)
        m.d.sync += src_l.s.eq(Repl(self.issue_i, self.n_src))
        m.d.sync += src_l.r.eq(reset_r)

        # dest operand latch (not using issue_i)
        m.d.sync += req_l.s.eq(Repl(all_rd, self.n_dst))
        m.d.sync += req_l.r.eq(reset_w)

        # create a latch/register for the operand
        oper_r = self.opsubsetkls(name="oper_r")
        latchregister(m, self.oper_i, oper_r, self.issue_i, "oper_l")

        # and for each output from the ALU
        drl = []
        for i in range(self.n_dst):
            name = "data_r%d" % i
            data_r = Signal(self.cu._get_dstwid(i), name=name, reset_less=True)
            latchregister(m, self.get_out(i), data_r, req_l.q[i], name + "_l")
            drl.append(data_r)

        # pass the operation to the ALU
        m.d.comb += self.get_op().eq(oper_r)

        # create list of src/alu-src/src-latch.  override 1st and 2nd one below.
        # in the case, for ALU and Logical pipelines, we assume RB is the
        # 2nd operand in the input "regspec".  see for example
        # soc.fu.alu.pipe_data.ALUInputData
        sl = []
        print ("src_i", self.src_i)
        for i in range(self.n_src):
            sl.append([self.src_i[i], self.get_in(i), src_l.q[i], Const(1,1)])

        # if the operand subset has "zero_a" we implicitly assume that means
        # src_i[0] is an INT reg type where zero can be multiplexed in, instead.
        # see https://bugs.libre-soc.org/show_bug.cgi?id=336
        if hasattr(oper_r, "zero_a"):
            # select zero imm if opcode says so.  however also change the latch
            # to trigger *from* the opcode latch instead.
            self._mux_op(m, sl, oper_r.zero_a, 0, 0)

        # if the operand subset has "imm_data" we implicitly assume that means
        # "this is an INT ALU/Logical FU jobbie, RB is muxed with the immediate"
        if hasattr(oper_r, "imm_data"):
            # select immediate if opcode says so. however also change the latch
            # to trigger *from* the opcode latch instead.
            op_is_imm = oper_r.imm_data.imm_ok
            imm = oper_r.imm_data.imm
            self._mux_op(m, sl, op_is_imm, imm, 1)

        # create a latch/register for src1/src2 (even if it is a copy of imm)
        for i in range(self.n_src):
            src, alusrc, latch, _ = sl[i]
            latchregister(m, src, alusrc, latch, name="src_r%d" % i)

        # -----
        # outputs
        # -----

        slg = Cat(*map(lambda x: x[3], sl)) # get req gate conditions
        # all request signals gated by busy_o.  prevents picker problems
        m.d.comb += self.busy_o.eq(opc_l.q) # busy out
        bro = Repl(self.busy_o, self.n_src)
        m.d.comb += self.rd.rel.eq(src_l.q & bro & slg) # src1/src2 req rel

        # on a go_read, tell the ALU we're accepting data.
        # NOTE: this spells TROUBLE if the ALU isn't ready!
        # go_read is only valid for one clock!
        with m.If(all_rd):                           # src operands ready, GO!
            with m.If(~self.alu.p.ready_o):          # no ACK yet
                m.d.comb += self.alu.p.valid_i.eq(1) # so indicate valid

        brd = Repl(self.busy_o & self.shadown_i, self.n_dst)
        # only proceed if ALU says its output is valid
        with m.If(self.alu.n.valid_o):
            # when ALU ready, write req release out. waits for shadow
            m.d.comb += self.wr.rel.eq(req_l.q & brd)
            # when output latch is ready, and ALU says ready, accept ALU output
            with m.If(reset):
                m.d.comb += self.alu.n.ready_i.eq(1) # tells ALU "got it"

        # output the data from the latch on go_write
        for i in range(self.n_dst):
            with m.If(self.wr.go[i]):
                m.d.comb += self.dest[i].eq(drl[i])

        return m

    def __iter__(self):
        yield self.rd.go
        yield self.wr.go
        yield self.issue_i
        yield self.shadown_i
        yield self.go_die_i
        yield from self.oper_i.ports()
        yield self.src1_i
        yield self.src2_i
        yield self.busy_o
        yield self.rd.rel
        yield self.wr.rel
        yield self.data_o

    def ports(self):
        return list(self)


def op_sim(dut, a, b, op, inv_a=0, imm=0, imm_ok=0, zero_a=0):
    yield dut.issue_i.eq(0)
    yield
    yield dut.src_i[0].eq(a)
    yield dut.src_i[1].eq(b)
    yield dut.oper_i.insn_type.eq(op)
    yield dut.oper_i.invert_a.eq(inv_a)
    yield dut.oper_i.imm_data.imm.eq(imm)
    yield dut.oper_i.imm_data.imm_ok.eq(imm_ok)
    yield dut.oper_i.zero_a.eq(zero_a)
    yield dut.issue_i.eq(1)
    yield
    yield dut.issue_i.eq(0)
    yield
    if not imm_ok or not zero_a:
        yield dut.rd.go.eq(0b11)
        while True:
            yield
            rd_rel_o = yield dut.rd.rel
            print ("rd_rel", rd_rel_o)
            if rd_rel_o:
                break
        yield dut.rd.go.eq(0)
    req_rel_o = yield dut.wr.rel
    result = yield dut.data_o
    print ("req_rel", req_rel_o, result)
    while True:
        req_rel_o = yield dut.wr.rel
        result = yield dut.data_o
        print ("req_rel", req_rel_o, result)
        if req_rel_o:
            break
        yield
    yield dut.wr.go[0].eq(1)
    yield
    result = yield dut.data_o
    print ("result", result)
    yield dut.wr.go[0].eq(0)
    yield
    return result


def scoreboard_sim(dut):
    result = yield from op_sim(dut, 5, 2, InternalOp.OP_ADD, inv_a=0,
                                    imm=8, imm_ok=1)
    assert result == 13

    result = yield from op_sim(dut, 5, 2, InternalOp.OP_ADD)
    assert result == 7

    result = yield from op_sim(dut, 5, 2, InternalOp.OP_ADD, inv_a=1)
    assert result == 65532

    result = yield from op_sim(dut, 5, 2, InternalOp.OP_ADD, zero_a=1,
                                    imm=8, imm_ok=1)
    assert result == 8

    result = yield from op_sim(dut, 5, 2, InternalOp.OP_ADD, zero_a=1)
    assert result == 2


def test_compunit():
    from alu_hier import ALU
    from soc.fu.alu.alu_input_record import CompALUOpSubset

    m = Module()
    alu = ALU(16)
    dut = MultiCompUnit(16, alu, CompALUOpSubset)
    m.submodules.cu = dut

    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_compunit1.il", "w") as f:
        f.write(vl)

    run_simulation(m, scoreboard_sim(dut), vcd_name='test_compunit1.vcd')


class CompUnitParallelTest:
    def __init__(self, dut):
        self.dut = dut

        # Operation cycle should not take longer than this:
        self.MAX_BUSY_WAIT = 50

        # Minimum duration in which issue_i will be kept inactive,
        # during which busy_o must remain low.
        self.MIN_BUSY_LOW = 5

        # store common data for the input operation of the processes
        # input operation:
        self.op = 0
        self.inv_a = self.zero_a = 0
        self.imm = self.imm_ok = 0
        # input data:
        self.a = self.b = 0

    def driver(self):
        print("Begin parallel test.")
        yield from self.operation(5, 2, InternalOp.OP_ADD, inv_a=0,
                                  imm=8, imm_ok=1)

    def operation(self, a, b, op, inv_a=0, imm=0, imm_ok=0, zero_a=0):
        # store data for the operation
        self.a = a
        self.b = b
        self.op = op
        self.inv_a = inv_a
        self.imm = imm
        self.imm_ok = imm_ok
        self.zero_a = zero_a

        # trigger operation cycle
        yield from self.issue()

    def issue(self):
        # issue_i starts inactive
        yield self.dut.issue_i.eq(0)

        for n in range(self.MIN_BUSY_LOW):
            yield
            # busy_o must remain inactive. It cannot rise on its own.
            busy_o = yield self.dut.busy_o
            assert not busy_o

        # activate issue_i to begin the operation cycle
        yield self.dut.issue_i.eq(1)

        # at the same time, present the operation
        yield self.dut.oper_i.insn_type.eq(self.op)
        yield self.dut.oper_i.invert_a.eq(self.inv_a)
        yield self.dut.oper_i.imm_data.imm.eq(self.imm)
        yield self.dut.oper_i.imm_data.imm_ok.eq(self.imm_ok)
        yield self.dut.oper_i.zero_a.eq(self.zero_a)

        # give one cycle for the CompUnit to latch the data
        yield

        # busy_o must keep being low in this cycle, because issue_i was
        # low on the previous cycle.
        # It cannot rise on its own.
        # Also, busy_o and issue_i must never be active at the same time, ever.
        busy_o = yield self.dut.busy_o
        assert not busy_o

        # Lower issue_i
        yield self.dut.issue_i.eq(0)

        # deactivate inputs along with issue_i, so we can be sure the data
        # was latched at the correct cycle
        yield self.dut.oper_i.insn_type.eq(0)
        yield self.dut.oper_i.invert_a.eq(0)
        yield self.dut.oper_i.imm_data.imm.eq(0)
        yield self.dut.oper_i.imm_data.imm_ok.eq(0)
        yield self.dut.oper_i.zero_a.eq(0)
        yield

        # wait for busy_o to lower
        # timeout after self.MAX_BUSY_WAIT cycles
        for n in range(self.MAX_BUSY_WAIT):
            # sample busy_o in the current cycle
            busy_o = yield self.dut.busy_o
            if not busy_o:
                # operation cycle ends when busy_o becomes inactive
                break
            yield

        # if busy_o is still active, a timeout has occurred
        # TODO: Uncomment this, once the test is complete:
        # assert not busy_o

        if busy_o:
            print("If you are reading this, "
                  "it's because the above test failed, as expected,\n"
                  "with a timeout. It must pass, once the test is complete.")
            return

        print("If you are reading this, "
              "it's because the above test unexpectedly passed.")

    def rd(self, rd_idx):
        # wait for issue_i to rise
        while True:
            issue_i = yield self.dut.issue_i
            if issue_i:
                break
            # issue_i has not risen yet, so rd must keep low
            rd = yield self.dut.rd.rel[rd_idx]
            assert not rd
            yield

        # we do not want rd to rise on an immediate operand
        # if it is immediate, exit the process
        # TODO: don't exit the process, monitor rd instead to ensure it
        #       doesn't rise on its own
        if (self.zero_a and rd_idx == 0) or (self.imm_ok and rd_idx == 1):
            return

        # issue_i has risen. rd must rise on the next cycle
        rd = yield self.dut.rd.rel[rd_idx]
        assert not rd
        yield
        rd = yield self.dut.rd.rel[rd_idx]
        assert rd

        # TODO: set dut.rd.go[idx] for one cycle
        yield
        # TODO: also when dut.rd.go is set, put the expected value into
        # the src_i.  use dut.get_in[rd_idx] to do so

    def wr(self, wr_idx):
        # monitor self.dut.wr.req[rd_idx] and sets dut.wr.go[idx] for one cycle
        yield
        # TODO: also when dut.wr.go is set, check the output against the
        # self.expected_o and assert.  use dut.get_out(wr_idx) to do so.

    def run_simulation(self, vcd_name):
        run_simulation(self.dut, [self.driver(),
                                  self.rd(0),  # one read port (a)
                                  self.rd(1),  # one read port (b)
                                  self.wr(0),  # one write port (o)
                                  ],
                       vcd_name=vcd_name)


def test_compunit_regspec1():
    from alu_hier import ALU
    from soc.fu.alu.alu_input_record import CompALUOpSubset

    inspec = [('INT', 'a', '0:15'),
              ('INT', 'b', '0:15')]
    outspec = [('INT', 'o', '0:15'),
              ]

    regspec = (inspec, outspec)

    m = Module()
    alu = ALU(16)
    dut = MultiCompUnit(regspec, alu, CompALUOpSubset)
    m.submodules.cu = dut

    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_compunit_regspec1.il", "w") as f:
        f.write(vl)

    run_simulation(m, scoreboard_sim(dut),
                   vcd_name='test_compunit_regspec1.vcd')

    test = CompUnitParallelTest(dut)
    test.run_simulation("test_compunit_parallel.vcd")


if __name__ == '__main__':
    test_compunit()
    test_compunit_regspec1()
