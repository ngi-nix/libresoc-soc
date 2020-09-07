"""Computation Unit (aka "ALU Manager").

Manages a Pipeline or FSM, ensuring that the start and end time are 100%
monitored.  At no time may the ALU proceed without this module notifying
the Dependency Matrices.  At no time is a result production "abandoned".
This module blocks (indicates busy) starting from when it first receives
an opcode until it receives notification that
its result(s) have been successfully stored in the regfile(s)

Documented at http://libre-soc.org/3d_gpu/architecture/compunit
"""

from nmigen import Module, Signal, Mux, Elaboratable, Repl, Cat, Const
from nmigen.hdl.rec import (Record, DIR_FANIN, DIR_FANOUT)

from nmutil.latch import SRLatch, latchregister
from nmutil.iocontrol import RecordObject
from nmutil.util import rising_edge

from soc.fu.regspec import RegSpec, RegSpecALUAPI


def find_ok(fields):
    """find_ok helper function - finds field ending in "_ok"
    """
    for field_name in fields:
        if field_name.endswith("_ok"):
            return field_name
    return None


def go_record(n, name):
    r = Record([('go_i', n, DIR_FANIN),
                ('rel_o', n, DIR_FANOUT)], name=name)
    r.go_i.reset_less = True
    r.rel_o.reset_less = True
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
        print ("name", name)
        RecordObject.__init__(self)
        self._subkls = subkls
        n_src, n_dst = self._n_src, self._n_dst

        # create source operands
        src = []
        for i in range(n_src):
            j = i + 1  # name numbering to match src1/src2
            sname = "src%d_i" % j
            rw = self._get_srcwid(i)
            sreg = Signal(rw, name=sname, reset_less=True)
            setattr(self, sname, sreg)
            src.append(sreg)
        self._src_i = src

        # create dest operands
        dst = []
        for i in range(n_dst):
            j = i + 1  # name numbering to match dest1/2...
            dname = "dest%d_o" % j
            rw = self._get_dstwid(i)
            # dreg = Data(rw, name=name) XXX ??? output needs to be a Data type?
            dreg = Signal(rw, name=dname, reset_less=True)
            setattr(self, dname, dreg)
            dst.append(dreg)
        self._dest = dst

        # operation / data input
        self.oper_i = subkls(name="oper_i_%s" % name)  # operand

        # create read/write and other scoreboard signalling
        self.rd = go_record(n_src, name="cu_rd")  # read in, req out
        self.wr = go_record(n_dst, name="cu_wr")  # write in, req out
        # read / write mask
        self.rdmaskn = Signal(n_src, name="cu_rdmaskn_i", reset_less=True)
        self.wrmask = Signal(n_dst, name="cu_wrmask_o", reset_less=True)

        # fn issue in
        self.issue_i = Signal(name="cu_issue_i", reset_less=True)
        # shadow function, defaults to ON
        self.shadown_i = Signal(name="cu_shadown_i", reset=1)
        # go die (reset)
        self.go_die_i = Signal(name="cu_go_die_i")

        # output (busy/done)
        self.busy_o = Signal(name="cu_busy_o", reset_less=True)  # fn busy out
        self.done_o = Signal(name="cu_done_o", reset_less=True)


class MultiCompUnit(RegSpecALUAPI, Elaboratable):
    def __init__(self, rwid, alu, opsubsetkls, n_src=2, n_dst=1, name=None):
        """MultiCompUnit

        * :rwid:        width of register latches (TODO: allocate per regspec)
        * :alu:         ALU (pipeline, FSM) - must conform to nmutil Pipe API
        * :opsubsetkls: subset of Decode2ExecuteType
        * :n_src:       number of src operands
        * :n_dst:       number of destination operands
        """
        RegSpecALUAPI.__init__(self, rwid, alu)
        self.alu_name = name or "alu"
        self.opsubsetkls = opsubsetkls
        self.cu = cu = CompUnitRecord(opsubsetkls, rwid, n_src, n_dst,
                                      name=name)
        n_src, n_dst = self.n_src, self.n_dst = cu._n_src, cu._n_dst
        print("n_src %d n_dst %d" % (self.n_src, self.n_dst))

        # convenience names for src operands
        for i in range(n_src):
            j = i + 1  # name numbering to match src1/src2
            name = "src%d_i" % j
            setattr(self, name, getattr(cu, name))

        # convenience names for dest operands
        for i in range(n_dst):
            j = i + 1  # name numbering to match dest1/2...
            name = "dest%d_o" % j
            setattr(self, name, getattr(cu, name))

        # more convenience names
        self.rd = cu.rd
        self.wr = cu.wr
        self.rdmaskn = cu.rdmaskn
        self.wrmask = cu.wrmask
        self.go_rd_i = self.rd.go_i  # temporary naming
        self.go_wr_i = self.wr.go_i  # temporary naming
        self.rd_rel_o = self.rd.rel_o  # temporary naming
        self.req_rel_o = self.wr.rel_o  # temporary naming
        self.issue_i = cu.issue_i
        self.shadown_i = cu.shadown_i
        self.go_die_i = cu.go_die_i

        # operation / data input
        self.oper_i = cu.oper_i
        self.src_i = cu._src_i

        self.busy_o = cu.busy_o
        self.dest = cu._dest
        self.data_o = self.dest[0]  # Dest out
        self.done_o = cu.done_o

    def _mux_op(self, m, sl, op_is_imm, imm, i):
        # select imm if opcode says so. however also change the latch
        # to trigger *from* the opcode latch instead.
        src_or_imm = Signal(self.cu._get_srcwid(i), reset_less=True)
        src_sel = Signal(reset_less=True)
        m.d.comb += src_sel.eq(Mux(op_is_imm, self.opc_l.q, sl[i][2]))
        m.d.comb += src_or_imm.eq(Mux(op_is_imm, imm, self.src_i[i]))
        # overwrite 1st src-latch with immediate-muxed stuff
        sl[i][0] = src_or_imm
        sl[i][2] = src_sel
        sl[i][3] = ~op_is_imm  # change rd.rel[i] gate condition

    def elaborate(self, platform):
        m = Module()
        setattr(m.submodules, self.alu_name, self.alu)
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
                              (((~self.rd.rel_o) | self.rd.go_i).all()))

        # generate read-done pulse
        all_rd_pulse = Signal(reset_less=True)
        m.d.comb += all_rd_pulse.eq(rising_edge(m, all_rd))

        # create rising pulse from alu valid condition.
        alu_done = Signal(reset_less=True)
        alu_pulse = Signal(reset_less=True)
        alu_pulsem = Signal(self.n_dst, reset_less=True)
        m.d.comb += alu_done.eq(self.alu.n.valid_o)
        m.d.comb += alu_pulse.eq(rising_edge(m, alu_done))
        m.d.comb += alu_pulsem.eq(Repl(alu_pulse, self.n_dst))

        # sigh bug where req_l gets both set and reset raised at same time
        prev_wr_go = Signal(self.n_dst)
        brd = Repl(self.busy_o, self.n_dst)
        m.d.sync += prev_wr_go.eq(self.wr.go_i & brd)

        # write_requests all done
        # req_done works because any one of the last of the writes
        # is enough, when combined with when read-phase is done (rst_l.q)
        wr_any = Signal(reset_less=True)
        req_done = Signal(reset_less=True)
        m.d.comb += self.done_o.eq(self.busy_o &
                                   ~((self.wr.rel_o & ~self.wrmask).bool()))
        m.d.comb += wr_any.eq(self.wr.go_i.bool() | prev_wr_go.bool())
        m.d.comb += req_done.eq(wr_any & ~self.alu.n.ready_i &
                                ((req_l.q & self.wrmask) == 0))
        # argh, complicated hack: if there are no regs to write,
        # instead of waiting for regs that are never going to happen,
        # we indicate "done" when the ALU is "done"
        with m.If((self.wrmask == 0) &
                  self.alu.n.ready_i & self.alu.n.valid_o & self.busy_o):
            m.d.comb += req_done.eq(1)

        # shadow/go_die
        reset = Signal(reset_less=True)
        rst_r = Signal(reset_less=True)  # reset latch off
        reset_w = Signal(self.n_dst, reset_less=True)
        reset_r = Signal(self.n_src, reset_less=True)
        m.d.comb += reset.eq(req_done | self.go_die_i)
        m.d.comb += rst_r.eq(self.issue_i | self.go_die_i)
        m.d.comb += reset_w.eq(self.wr.go_i | Repl(self.go_die_i, self.n_dst))
        m.d.comb += reset_r.eq(self.rd.go_i | Repl(self.go_die_i, self.n_src))

        # read-done,wr-proceed latch
        m.d.sync += rok_l.s.eq(self.issue_i)  # set up when issue starts
        m.d.sync += rok_l.r.eq(self.alu.n.valid_o & self.busy_o)  # ALU done

        # wr-done, back-to-start latch
        m.d.sync += rst_l.s.eq(all_rd)     # set when read-phase is fully done
        m.d.sync += rst_l.r.eq(rst_r)        # *off* on issue

        # opcode latch (not using go_rd_i) - inverted so that busy resets to 0
        m.d.sync += opc_l.s.eq(self.issue_i)       # set on issue
        m.d.sync += opc_l.r.eq(req_done)  # reset on ALU

        # src operand latch (not using go_wr_i)
        m.d.sync += src_l.s.eq(Repl(self.issue_i, self.n_src))
        m.d.sync += src_l.r.eq(reset_r)

        # dest operand latch (not using issue_i)
        m.d.sync += req_l.s.eq(alu_pulsem & self.wrmask)
        m.d.sync += req_l.r.eq(reset_w | prev_wr_go)

        # pass operation to the ALU (sync: plenty time to wait for src reads)
        op = self.get_op()
        with m.If(self.issue_i):
            m.d.sync += op.eq(self.oper_i)

        # and for each output from the ALU: capture when ALU output is valid
        drl = []
        wrok = []
        for i in range(self.n_dst):
            name = "data_r%d" % i
            lro = self.get_out(i)
            ok = Const(1, 1)
            if isinstance(lro, Record):
                data_r = Record.like(lro, name=name)
                print("wr fields", i, lro, data_r.fields)
                # bye-bye abstract interface design..
                fname = find_ok(data_r.fields)
                if fname:
                    ok = getattr(lro, fname)
            else:
                data_r = Signal.like(lro, name=name, reset_less=True)
            wrok.append(ok & self.busy_o)
            with m.If(alu_pulse):
                m.d.sync += data_r.eq(lro)
            with m.If(self.issue_i):
                m.d.sync += data_r.eq(0)
            drl.append(data_r)

        # ok, above we collated anything with an "ok" on the output side
        # now actually use those to create a write-mask.  this basically
        # is now the Function Unit API tells the Comp Unit "do not request
        # a regfile port because this particular output is not valid"
        m.d.comb += self.wrmask.eq(Cat(*wrok))

        # create list of src/alu-src/src-latch.  override 1st and 2nd one below.
        # in the case, for ALU and Logical pipelines, we assume RB is the
        # 2nd operand in the input "regspec".  see for example
        # soc.fu.alu.pipe_data.ALUInputData
        sl = []
        print("src_i", self.src_i)
        for i in range(self.n_src):
            sl.append([self.src_i[i], self.get_in(i), src_l.q[i], Const(1, 1)])

        # if the operand subset has "zero_a" we implicitly assume that means
        # src_i[0] is an INT reg type where zero can be multiplexed in, instead.
        # see https://bugs.libre-soc.org/show_bug.cgi?id=336
        if hasattr(op, "zero_a"):
            # select zero imm if opcode says so.  however also change the latch
            # to trigger *from* the opcode latch instead.
            self._mux_op(m, sl, op.zero_a, 0, 0)

        # if the operand subset has "imm_data" we implicitly assume that means
        # "this is an INT ALU/Logical FU jobbie, RB is muxed with the immediate"
        if hasattr(op, "imm_data"):
            # select immediate if opcode says so. however also change the latch
            # to trigger *from* the opcode latch instead.
            op_is_imm = op.imm_data.ok
            imm = op.imm_data.data
            self._mux_op(m, sl, op_is_imm, imm, 1)

        # create a latch/register for src1/src2 (even if it is a copy of imm)
        for i in range(self.n_src):
            src, alusrc, latch, _ = sl[i]
            latchregister(m, src, alusrc, latch, name="src_r%d" % i)

        # -----
        # ALU connection / interaction
        # -----

        # on a go_read, tell the ALU we're accepting data.
        m.submodules.alui_l = alui_l = SRLatch(False, name="alui")
        m.d.comb += self.alu.p.valid_i.eq(alui_l.q)
        m.d.sync += alui_l.r.eq(self.alu.p.ready_o & alui_l.q)
        m.d.comb += alui_l.s.eq(all_rd_pulse)

        # ALU output "ready" side.  alu "ready" indication stays hi until
        # ALU says "valid".
        m.submodules.alu_l = alu_l = SRLatch(False, name="alu")
        m.d.comb += self.alu.n.ready_i.eq(alu_l.q)
        m.d.sync += alu_l.r.eq(self.alu.n.valid_o & alu_l.q)
        m.d.comb += alu_l.s.eq(all_rd_pulse)

        # -----
        # outputs
        # -----

        slg = Cat(*map(lambda x: x[3], sl))  # get req gate conditions
        # all request signals gated by busy_o.  prevents picker problems
        m.d.comb += self.busy_o.eq(opc_l.q)  # busy out

        # read-release gated by busy (and read-mask)
        bro = Repl(self.busy_o, self.n_src)
        m.d.comb += self.rd.rel_o.eq(src_l.q & bro & slg & ~self.rdmaskn)

        # write-release gated by busy and by shadow (and write-mask)
        brd = Repl(self.busy_o & self.shadown_i, self.n_dst)
        m.d.comb += self.wr.rel_o.eq(req_l.q & brd & self.wrmask)

        # output the data from the latch on go_write
        for i in range(self.n_dst):
            with m.If(self.wr.go_i[i] & self.busy_o):
                m.d.comb += self.dest[i].eq(drl[i])

        return m

    def get_fu_out(self, i):
        return self.dest[i]

    def __iter__(self):
        yield self.rd.go_i
        yield self.wr.go_i
        yield self.issue_i
        yield self.shadown_i
        yield self.go_die_i
        yield from self.oper_i.ports()
        yield self.src1_i
        yield self.src2_i
        yield self.busy_o
        yield self.rd.rel_o
        yield self.wr.rel_o
        yield self.data_o

    def ports(self):
        return list(self)
