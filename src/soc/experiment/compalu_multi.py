from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Mux, Elaboratable, Repl, Array, Record
from nmigen.hdl.rec import (DIR_FANIN, DIR_FANOUT)

from nmutil.latch import SRLatch, latchregister
from nmutil.iocontrol import RecordObject

from soc.decoder.power_decoder2 import Data
from soc.decoder.power_enums import InternalOp


""" Computation Unit (aka "ALU Manager").

    This module runs a "revolving door" set of three latches, based on
    * Issue
    * Go_Read
    * Go_Write
    where one of them cannot be set on any given cycle.

    * When issue is first raised, a busy signal is sent out.
      The src1 and src2 registers and the operand can be latched in
      at this point

    * Read request is set, which is acknowledged through the Scoreboard
      to the priority picker, which generates (one and only one) Go_Read
      at a time.  One of those will (eventually) be this Computation Unit.

    * Once Go_Read is set, the src1/src2/operand latch door shuts (locking
      src1/src2/operand in place), and the ALU is told to proceed.

    * when the ALU pipeline is ready, this activates "write request release",
      and the ALU's output is captured into a temporary register.

    * Write request release is *HELD UP* (prevented from proceeding) if shadowN
      is asserted LOW.  This is how all speculation, precise exceptions,
      predication - everything - is achieved.

    * Write request release will go through a similar process as Read request,
      resulting (eventually) in Go_Write being asserted.

    * When Go_Write is asserted, two things happen: (1) the data in the temp
      register is placed combinatorially onto the output, and (2) the
      req_l latch is cleared, busy is dropped, and the Comp Unit is back
      through its revolving door to do another task.

    Note that the read and write latches are held synchronously for one cycle,
    i.e. that when Go_Read comes in, one cycle is given in which the incoming
    register (broadcast over a Regfile Read Port) may have time to be latched.

    It is REQUIRED that Go_Read be held valid only for one cycle, and it is
    REQUIRED that the corresponding Read_Req be dropped exactly one cycle after
    Go_Read is asserted HI.

    Likewise for Go_Write: this is asserted for one cycle, and Req_Writes must
    likewise be dropped exactly one cycle after assertion of Go_Write.

    When Go_Die is asserted then strictly speaking the entire FSM should be
    fully reset and that includes sending a cancellation request to the ALU.
    (XXX TODO: alu "go die" is not presently wired up)
"""

def go_record(n, name):
    r = Record([('go', n, DIR_FANIN),
                ('rel', n, DIR_FANOUT)], name=name)
    r.go.reset_less = True
    r.rel.reset_less = True
    return r

# see https://libre-soc.org/3d_gpu/architecture/regfile/ section on regspecs
def get_regspec_bitwidth(regspec, srcdest, idx):
    bitspec = regspec[srcdest][idx]
    wid = 0
    print (bitspec)
    for ranges in bitspec[2].split(","):
        ranges = ranges.split(":")
        print (ranges)
        if len(ranges) == 1: # only one bit
            wid += 1
        else:
            start, end = map(int, ranges)
            wid += (end-start)+1
    return wid


class CompUnitRecord(RecordObject):
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
        RecordObject.__init__(self, name)
        self._rwid = rwid
        if isinstance(rwid, int):
            # rwid: integer (covers all registers)
            self._n_src, self._n_dst = n_src, n_dst
        else:
            # rwid: a regspec.
            self._n_src, self._n_dst = len(rwid[0]), len(rwid[1])
        self._subkls = subkls

        src = []
        for i in range(n_src):
            j = i + 1 # name numbering to match src1/src2
            name = "src%d_i" % j
            rw = self._get_srcwid(i)
            sreg = Signal(rw, name=name, reset_less=True)
            setattr(self, name, sreg)
            src.append(sreg)
        self._src_i = src

        dst = []
        for i in range(n_dst):
            j = i + 1 # name numbering to match dest1/2...
            name = "dest%d_i" % j
            rw = self._get_dstwid(i)
            dreg = Signal(rw, name=name, reset_less=True)
            setattr(self, name, dreg)
            dst.append(dreg)
        self._dest = dst

        self.rd = go_record(n_src, name="rd") # read in, req out
        self.wr = go_record(n_dst, name="wr") # write in, req out
        self.issue_i = Signal(reset_less=True) # fn issue in
        self.shadown_i = Signal(reset=1) # shadow function, defaults to ON
        self.go_die_i = Signal() # go die (reset)

        # operation / data input
        self.oper_i = subkls() # operand

        # output (busy/done)
        self.busy_o = Signal(reset_less=True) # fn busy out
        self.done_o = Signal(reset_less=True)

    def _get_dstwid(self, i):
        if isinstance(self._rwid, int):
            return self._rwid
        return get_regspec_bitwidth(self._rwid, 1, i)

    def _get_srcwid(self, i):
        if isinstance(self._rwid, int):
            return self._rwid
        return get_regspec_bitwidth(self._rwid, 0, i)


class RegSpecALUAPI:
    def __init__(self, rwid, alu):
        """RegSpecAPI

        * :rwid:       regspec
        * :alu:        ALU covered by this regspec
        """
        self.rwid = rwid
        self.alu = alu # actual ALU - set as a "submodule" of the CU

    def get_out(self, i):
        if isinstance(self.rwid, int): # old - testing - API (rwid is int)
            return self.alu.out[i]
        # regspec-based API: look up variable through regspec according to row number
        return getattr(self.alu.n.data_o, self.rwid[1][i][1])

    def get_in(self, i):
        if isinstance(self.rwid, int): # old - testing - API (rwid is int)
            return self.alu.i[i]
        # regspec-based API: look up variable through regspec according to row number
        return getattr(self.alu.p.data_i, self.rwid[0][i][1])

    def get_op(self):
        if isinstance(self.rwid, int): # old - testing - API (rwid is int)
            return self.alu.op
        return self.alu.p.data_i.ctx.op


class MultiCompUnit(RegSpecALUAPI, Elaboratable):
    def __init__(self, rwid, alu, opsubsetkls, n_src=2, n_dst=1):
        """MultiCompUnit

        * :rwid:        width of register latches (TODO: allocate per regspec)
        * :alu:         the ALU (pipeline, FSM) - must conform to nmutil Pipe API
        * :opsubsetkls: the subset of Decode2ExecuteType
        * :n_src:       number of src operands
        * :n_dst:       number of destination operands
        """
        RegSpecALUAPI.__init__(self, rwid, alu)
        self.n_src, self.n_dst = n_src, n_dst
        self.opsubsetkls = opsubsetkls
        self.cu = cu = CompUnitRecord(opsubsetkls, rwid, n_src, n_dst)

        for i in range(n_src):
            j = i + 1 # name numbering to match src1/src2
            name = "src%d_i" % j
            setattr(self, name, getattr(cu, name))

        for i in range(n_dst):
            j = i + 1 # name numbering to match dest1/2...
            name = "dest%d_i" % j
            setattr(self, name, getattr(cu, name))

        # convenience names
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

    def elaborate(self, platform):
        m = Module()
        m.submodules.alu = self.alu
        m.submodules.src_l = src_l = SRLatch(False, self.n_src, name="src")
        m.submodules.opc_l = opc_l = SRLatch(sync=False, name="opc")
        m.submodules.req_l = req_l = SRLatch(False, self.n_dst, name="req")
        m.submodules.rst_l = rst_l = SRLatch(sync=False, name="rst")
        m.submodules.rok_l = rok_l = SRLatch(sync=False, name="rdok")

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
        oper_r = self.opsubsetkls()
        latchregister(m, self.oper_i, oper_r, self.issue_i, "oper_r")

        # and for each output from the ALU
        drl = []
        for i in range(self.n_dst):
            name = "data_r%d" % i
            data_r = Signal(self.cu._get_srcwid(i), name=name, reset_less=True)
            latchregister(m, self.get_out(i), data_r, req_l.q[i], name)
            drl.append(data_r)

        # pass the operation to the ALU
        m.d.comb += self.get_op().eq(oper_r)

        # create list of src/alu-src/src-latch.  override 1st and 2nd one below.
        # in the case, for ALU and Logical pipelines, we assume RB is the 2nd operand
        # in the input "regspec".  see for example soc.fu.alu.pipe_data.ALUInputData
        # TODO: assume RA is the 1st operand, zero_a detection is needed.
        sl = []
        for i in range(self.n_src):
            sl.append([self.src_i[i], self.get_in(i), src_l.q[i]])

        # if the operand subset has "zero_a" we implicitly assume that means
        # src_i[0] is an INT register type where zero can be multiplexed in, instead.
        # see https://bugs.libre-soc.org/show_bug.cgi?id=336
        #if hasattr(oper_r, "zero_a"):
            # select zero immediate if opcode says so.  however also change the latch
            # to trigger *from* the opcode latch instead.
            # ...
            # ...

        # if the operand subset has "imm_data" we implicitly assume that means
        # "this is an INT ALU/Logical FU jobbie, RB is multiplexed with the immediate"
        if hasattr(oper_r, "imm_data"):
            # select immediate if opcode says so.  however also change the latch
            # to trigger *from* the opcode latch instead.
            op_is_imm = oper_r.imm_data.imm_ok
            src2_or_imm = Signal(self.cu._get_srcwid(1), reset_less=True)
            src_sel = Signal(reset_less=True)
            m.d.comb += src_sel.eq(Mux(op_is_imm, opc_l.q, src_l.q[1]))
            m.d.comb += src2_or_imm.eq(Mux(op_is_imm, oper_r.imm_data.imm,
                                                      self.src2_i))
            # overwrite 2nd src-latch with immediate-muxed stuff
            sl[1][0] = src2_or_imm
            sl[1][2] = src_sel

        # create a latch/register for src1/src2 (even if it is a copy of an immediate)
        for i in range(self.n_src):
            src, alusrc, latch = sl[i]
            latchregister(m, src, alusrc, latch, name="src_r%d" % i)

        # -----
        # outputs
        # -----

        # all request signals gated by busy_o.  prevents picker problems
        m.d.comb += self.busy_o.eq(opc_l.q) # busy out
        bro = Repl(self.busy_o, self.n_src)
        m.d.comb += self.rd.rel.eq(src_l.q & bro) # src1/src2 req rel

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
                m.d.comb += self.alu.n.ready_i.eq(1) # tells ALU "thanks got it"

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


def op_sim(dut, a, b, op, inv_a=0, imm=0, imm_ok=0):
    yield dut.issue_i.eq(0)
    yield
    yield dut.src_i[0].eq(a)
    yield dut.src_i[1].eq(b)
    yield dut.oper_i.insn_type.eq(op)
    yield dut.oper_i.invert_a.eq(inv_a)
    yield dut.oper_i.imm_data.imm.eq(imm)
    yield dut.oper_i.imm_data.imm_ok.eq(imm_ok)
    yield dut.issue_i.eq(1)
    yield
    yield dut.issue_i.eq(0)
    yield
    yield dut.rd.go.eq(0b11)
    while True:
        yield
        rd_rel_o = yield dut.rd.rel
        print ("rd_rel", rd_rel_o)
        if rd_rel_o:
            break
    yield
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

    run_simulation(m, scoreboard_sim(dut), vcd_name='test_compunit1.vcd')


if __name__ == '__main__':
    test_compunit()
    test_compunit_regspec1()
