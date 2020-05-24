""" LOAD / STORE Computation Unit.  Also capable of doing ADD and ADD immediate

    This module runs a "revolving door" set of four latches, based on
    * Issue
    * Go_Read
    * Go_Addr
    * Go_Write *OR* Go_Store

    (Note that opc_l has been inverted (and qn used), due to SRLatch
     default reset state being "0" rather than "1")

    Also note: the LD/ST Comp Unit can act as a *standard ALU* doing
    add and subtract.

    Stores are activated when Go_Store is enabled, and uses the ALU
    to add the immediate (imm_i) to the address (src1_i), and then
    when ready (go_st_i and the ALU ready) the operand (src2_i) is stored
    in the computed address.
"""

from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Mux, Cat, Elaboratable, Array
from nmigen.hdl.rec import Record, Layout

from nmutil.latch import SRLatch, latchregister

from soc.experiment.compalu_multi import go_record
from soc.experiment.testmem import TestMemory
from soc.decoder.power_enums import InternalOp

from soc.experiment.alu_hier import CompALUOpSubset

from soc.decoder.power_enums import InternalOp, Function, CryIn

import operator


class CompLDSTOpSubset(Record):
    """CompLDSTOpSubset

    a copy of the relevant subset information from Decode2Execute1Type
    needed for LD/ST operations.  use with eq_from_execute1 (below) to
    grab subsets.
    """
    def __init__(self, name=None):
        layout = (('insn_type', InternalOp),
                  ('imm_data', Layout((("imm", 64), ("imm_ok", 1)))),
                  ('is_32bit', 1),
                  ('is_signed', 1),
                  ('data_len', 4), # TODO: should be in separate CompLDSTSubset
                  ('byte_reverse', 1),
                  ('sign_extend', 1),
                  ('update', 1))

        Record.__init__(self, Layout(layout), name=name)

        # grrr.  Record does not have kwargs
        self.insn_type.reset_less = True
        self.is_32bit.reset_less = True
        self.is_signed.reset_less = True
        self.data_len.reset_less = True
        self.byte_reverse.reset_less = True
        self.sign_extend.reset_less = True
        self.update.reset_less = True

    def eq_from_execute1(self, other):
        """ use this to copy in from Decode2Execute1Type
        """
        res = []
        for fname, sig in self.fields.items():
            eqfrom = other.fields[fname]
            res.append(sig.eq(eqfrom))
        return res

    def ports(self):
        return [self.insn_type,
                self.is_32bit,
                self.is_signed,
                self.data_len,
                self.byte_reverse,
                self.sign_extend,
                self.update,
        ]


class LDSTCompUnit(Elaboratable):
    """ LOAD / STORE / ADD / SUB Computation Unit

        Inputs
        ------

        * :rwid:   register width
        * :alu:    an ALU module
        * :mem:    a Memory Module (read-write capable)

        Control Signals (In)
        --------------------

        * :oper_i:     operation being carried out (LDST_OP_ADD, LDST_OP_LD)
        * :issue_i:    LD/ST is being "issued".
        * :isalu_i:    ADD/SUB is being "issued" (aka issue_alu_i)
        * :shadown_i:  Inverted-shadow is being held (stops STORE *and* WRITE)
        * :go_rd_i:    read is being actioned (latches in src regs)
        * :go_wr_i:    write mode (exactly like ALU CompUnit)
        * :go_ad_i:    address is being actioned (triggers actual mem LD)
        * :go_st_i:    store is being actioned (triggers actual mem STORE)
        * :go_die_i:   resets the unit back to "wait for issue"

        Control Signals (Out)
        ---------------------

        * :busy_o:      function unit is busy
        * :rd_rel_o:    request src1/src2
        * :adr_rel_o:   request address (from mem)
        * :sto_rel_o:   request store (to mem)
        * :req_rel_o:   request write (result)
        * :load_mem_o:  activate memory LOAD
        * :stwd_mem_o:  activate memory STORE

        Note: load_mem_o, stwd_mem_o and req_rel_o MUST all be acknowledged
        in a single cycle and the CompUnit set back to doing another op.
        This means deasserting go_st_i, go_ad_i or go_wr_i as appropriate
        depending on whether the operation is a STORE, LD, or a straight
        ALU operation respectively.

        Control Data (out)
        ------------------
        * :data_o:     Dest out (LD or ALU)
        * :addr_o:     Address out (LD or ST)
    """

    def __init__(self, rwid, alu, mem, n_src=2, n_dst=1, debugtest=False):
        self.rwid = rwid
        self.alu = alu
        self.mem = mem
        self.debugtest = debugtest

        self.counter = Signal(4)
        src = []
        for i in range(n_src):
            j = i + 1 # name numbering to match src1/src2
            src.append(Signal(rwid, name="src%d_i" % j, reset_less=True))

        dst = []
        for i in range(n_dst):
            j = i + 1 # name numbering to match dest1/2...
            dst.append(Signal(rwid, name="dest%d_i" % j, reset_less=True))

        self.rd = go_record(n_src, name="rd") # read in, req out
        self.wr = go_record(n_dst, name="wr") # write in, req out
        self.go_rd_i = self.rd.go # temporary naming
        self.go_wr_i = self.wr.go # temporary naming
        self.rd_rel_o = self.rd.rel # temporary naming
        self.req_rel_o = self.wr.rel # temporary naming

        self.go_ad_i = Signal(reset_less=True)  # go address in
        self.go_st_i = Signal(reset_less=True)  # go store in
        self.issue_i = Signal(reset_less=True)  # fn issue in
        self.isalu_i = Signal(reset_less=True)  # fn issue as ALU in
        self.shadown_i = Signal(reset=1)  # shadow function, defaults to ON
        self.go_die_i = Signal()  # go die (reset)

        # operation / data input
        self.oper_i = CompALUOpSubset() # operand
        self.src_i = Array(src)
        self.src1_i = src[0] # oper1 in
        self.src2_i = src[1] # oper2 in

        self.busy_o = Signal(reset_less=True)       # fn busy out
        self.dest = Array(dst)
        self.data_o = dst[0] # Dest out
        self.adr_rel_o = Signal(reset_less=True)  # request address (from mem)
        self.sto_rel_o = Signal(reset_less=True)  # request store (to mem)
        self.done_o = Signal(reset_less=True)  # final release signal
        self.data_o = Signal(rwid, reset_less=True)  # Dest out (LD or ALU)
        self.addr_o = Signal(rwid, reset_less=True)  # Address out (LD or ST)

        # hmm... TODO... move these to outside of LDSTCompUnit?
        self.load_mem_o = Signal(reset_less=True)  # activate memory LOAD
        self.stwd_mem_o = Signal(reset_less=True)  # activate memory STORE
        self.ld_o = Signal(reset_less=True)  # operation is a LD
        self.st_o = Signal(reset_less=True)  # operation is a ST

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        sync = m.d.sync

        m.submodules.alu = self.alu
        #m.submodules.mem = self.mem
        m.submodules.src_l = src_l = SRLatch(sync=False, name="src")
        m.submodules.opc_l = opc_l = SRLatch(sync=False, name="opc")
        m.submodules.adr_l = adr_l = SRLatch(sync=False, name="adr")
        m.submodules.req_l = req_l = SRLatch(sync=False, name="req")
        m.submodules.sto_l = sto_l = SRLatch(sync=False, name="sto")

        # shadow/go_die
        reset_b = Signal(reset_less=True)
        reset_w = Signal(reset_less=True)
        reset_a = Signal(reset_less=True)
        reset_s = Signal(reset_less=True)
        reset_r = Signal(reset_less=True)
        comb += reset_b.eq(self.go_st_i | self.wr.go |
                           self.go_ad_i | self.go_die_i)
        comb += reset_w.eq(self.wr.go | self.go_die_i)
        comb += reset_s.eq(self.go_st_i | self.go_die_i)
        comb += reset_r.eq(self.rd.go | self.go_die_i)
        # this one is slightly different, issue_alu_i selects wr.go)
        a_sel = Mux(self.isalu_i, self.wr.go, self.go_ad_i)
        comb += reset_a.eq(a_sel | self.go_die_i)

        # opcode decode
        op_alu = Signal(reset_less=True)
        op_is_ld = Signal(reset_less=True)
        op_is_st = Signal(reset_less=True)
        op_ldst = Signal(reset_less=True)
        op_is_imm = Signal(reset_less=True)

        # ALU/LD data output control
        alulatch = Signal(reset_less=True)
        ldlatch = Signal(reset_less=True)

        # src2 register
        src2_r = Signal(self.rwid, reset_less=True)

        # select immediate or src2 reg to add
        src2_or_imm = Signal(self.rwid, reset_less=True)
        src_sel = Signal(reset_less=True)

        # issue can be either issue_i or issue_alu_i (isalu_i)
        issue_i = Signal(reset_less=True)
        comb += issue_i.eq(self.issue_i | self.isalu_i)

        # Ripple-down the latches, each one set cancels the previous.
        # NOTE: use sync to stop combinatorial loops.

        # opcode latch - inverted so that busy resets to 0
        sync += opc_l.s.eq(issue_i)  # XXX NOTE: INVERTED FROM book!
        sync += opc_l.r.eq(reset_b)  # XXX NOTE: INVERTED FROM book!

        # src operand latch
        sync += src_l.s.eq(issue_i)
        sync += src_l.r.eq(reset_r)

        # addr latch
        sync += adr_l.s.eq(self.rd.go)
        sync += adr_l.r.eq(reset_a)

        # dest operand latch
        sync += req_l.s.eq(self.go_ad_i | self.go_st_i | self.wr.go)
        sync += req_l.r.eq(reset_w)

        # store latch
        sync += sto_l.s.eq(self.rd.go)  # XXX not sure which
        sync += sto_l.r.eq(reset_s)

        # create a latch/register for the operand
        oper_r = CompALUOpSubset()  # Dest register
        latchregister(m, self.oper_i, oper_r, self.issue_i, name="oper_l")

        # and one for the output from the ALU
        data_r = Signal(self.rwid, reset_less=True)  # Dest register
        latchregister(m, self.alu.o, data_r, alulatch, "aluo_r")

        # and pass the operation to the ALU
        comb += self.alu.op.eq(oper_r)
        comb += self.alu.op.insn_type.eq(InternalOp.OP_ADD) # override insn_type

        # outputs: busy and release signals
        busy_o = self.busy_o
        comb += self.busy_o.eq(opc_l.q)  # busy out
        comb += self.rd.rel.eq(src_l.q & busy_o)  # src1/src2 req rel
        comb += self.sto_rel_o.eq(sto_l.q & busy_o & self.shadown_i & op_is_st)

        # request release enabled based on if op is a LD/ST or a plain ALU
        # if op is an ADD/SUB or a LD, req_rel activates.
        wr_q = Signal(reset_less=True)
        comb += wr_q.eq(req_l.q & (~op_ldst | op_is_ld))

        comb += alulatch.eq((op_ldst & self.adr_rel_o) |
                            (~op_ldst & self.wr.rel))

        # select immediate if opcode says so.  however also change the latch
        # to trigger *from* the opcode latch instead.
        comb += src_sel.eq(Mux(op_is_imm, opc_l.qn, src_l.q))
        comb += src2_or_imm.eq(Mux(op_is_imm, oper_r.imm_data.imm,
                                              self.src2_i))

        # create a latch/register for src1/src2 (include immediate select)
        latchregister(m, self.src1_i, self.alu.a, src_l.q, name="src1_l")
        latchregister(m, self.src2_i, src2_r, src_l.q, name="src2_l")
        latchregister(m, src2_or_imm, self.alu.b, src_sel, name="imm_r")

        # decode bits of operand (latched)
        comb += op_is_imm.eq(oper_r.imm_data.imm_ok)
        comb += op_is_st.eq(oper_r.insn_type == InternalOp.OP_STORE)   # ST
        comb += op_is_ld.eq(oper_r.insn_type == InternalOp.OP_LOAD) # LD
        comb += op_ldst.eq(op_is_ld | op_is_st)
        comb += self.load_mem_o.eq(op_is_ld & self.go_ad_i)
        comb += self.stwd_mem_o.eq(op_is_st & self.go_st_i)
        comb += self.ld_o.eq(op_is_ld)
        comb += self.st_o.eq(op_is_st)

        # on a go_read, tell the ALU we're accepting data.
        # NOTE: this spells TROUBLE if the ALU isn't ready!
        # go_read is only valid for one clock!
        with m.If(self.rd.go):                     # src operands ready, GO!
            with m.If(~self.alu.p_ready_o):          # no ACK yet
                m.d.comb += self.alu.p_valid_i.eq(1)  # so indicate valid

        # only proceed if ALU says its output is valid
        with m.If(self.alu.n_valid_o):
            # write req release out.  waits until shadow is dropped.
            comb += self.wr.rel.eq(wr_q & busy_o & self.shadown_i)
            # address release only happens on LD/ST, and is shadowed.
            comb += self.adr_rel_o.eq(adr_l.q & op_ldst & busy_o &
                                      self.shadown_i)
            # when output latch is ready, and ALU says ready, accept ALU output
            with m.If(self.wr.rel):
                # tells ALU "thanks got it"
                m.d.comb += self.alu.n_ready_i.eq(1)

        # provide "done" signal: select req_rel for non-LD/ST, adr_rel for LD/ST
        comb += self.done_o.eq((self.wr.rel & ~op_ldst) |
                               (self.adr_rel_o & op_ldst))

        # put the register directly onto the output bus on a go_write
        # this is "ALU mode".  go_wr_i *must* be deasserted on next clock
        with m.If(self.wr.go):
            comb += self.data_o.eq(data_r)

        # "LD/ST" mode: put the register directly onto the *address* bus
        with m.If(self.go_ad_i | self.go_st_i):
            comb += self.addr_o.eq(data_r)

        # TODO: think about moving these to another module

        if self.debugtest:
            return m

        # connect ST to memory.  NOTE: unit *must* be set back
        # to start again by dropping go_st_i on next clock
        with m.If(self.stwd_mem_o):
            wrport = self.mem.wrport
            comb += wrport.addr.eq(self.addr_o)
            comb += wrport.data.eq(src2_r)
            comb += wrport.en.eq(1)

        # connect LD to memory.  NOTE: unit *must* be set back
        # to start again by dropping go_ad_i on next clock
        rdport = self.mem.rdport
        ldd_r = Signal(self.rwid, reset_less=True)  # Dest register
        # latch LD-out
        latchregister(m, rdport.data, ldd_r, ldlatch, "ldo_r")
        sync += ldlatch.eq(self.load_mem_o)
        with m.If(self.load_mem_o):
            comb += rdport.addr.eq(self.addr_o)
            # comb += rdport.en.eq(1) # only when transparent=False

        # if LD-latch, put ld-reg out onto output
        with m.If(ldlatch | self.load_mem_o):
            comb += self.data_o.eq(ldd_r)

        return m

    def __iter__(self):
        yield self.rd.go
        yield self.go_ad_i
        yield self.wr.go
        yield self.go_st_i
        yield self.issue_i
        yield self.isalu_i
        yield self.shadown_i
        yield self.go_die_i
        yield from self.oper_i.ports()
        yield from self.src_i
        yield self.busy_o
        yield self.rd.rel
        yield self.adr_rel_o
        yield self.sto_rel_o
        yield self.wr.rel
        yield self.data_o
        yield self.load_mem_o
        yield self.stwd_mem_o

    def ports(self):
        return list(self)


def wait_for(sig):
    v = (yield sig)
    print("wait for", sig, v)
    while True:
        yield
        v = (yield sig)
        print(v)
        if v:
            break


def store(dut, src1, src2, imm, imm_ok=True):
    yield dut.oper_i.insn_type.eq(InternalOp.OP_STORE)
    yield dut.src1_i.eq(src1)
    yield dut.src2_i.eq(src2)
    yield dut.oper_i.imm_data.imm.eq(imm)
    yield dut.oper_i.imm_data.imm_ok.eq(imm_ok)
    yield dut.issue_i.eq(1)
    yield
    yield dut.issue_i.eq(0)
    yield
    yield dut.rd.go.eq(0b11)
    yield from wait_for(dut.rd.rel)
    yield dut.rd.go.eq(0)
    yield from wait_for(dut.adr_rel_o)
    yield dut.go_st_i.eq(1)
    yield from wait_for(dut.sto_rel_o)
    wait_for(dut.stwd_mem_o)
    yield dut.go_st_i.eq(0)
    yield


def load(dut, src1, src2, imm, imm_ok=True):
    yield dut.oper_i.insn_type.eq(InternalOp.OP_LOAD)
    yield dut.src1_i.eq(src1)
    yield dut.src2_i.eq(src2)
    yield dut.oper_i.imm_data.imm.eq(imm)
    yield dut.oper_i.imm_data.imm_ok.eq(imm_ok)
    yield dut.issue_i.eq(1)
    yield
    yield dut.issue_i.eq(0)
    yield
    yield dut.rd.go.eq(0b11)
    yield from wait_for(dut.rd.rel)
    yield dut.rd.go.eq(0)
    yield from wait_for(dut.adr_rel_o)
    yield dut.go_ad_i.eq(1)
    yield from wait_for(dut.busy_o)
    yield
    data = (yield dut.data_o)
    yield dut.go_ad_i.eq(0)
    # wait_for(dut.stwd_mem_o)
    return data


def add(dut, src1, src2, imm, imm_ok=False):
    yield dut.oper_i.insn_type.eq(InternalOp.OP_ADD)
    yield dut.src1_i.eq(src1)
    yield dut.src2_i.eq(src2)
    yield dut.oper_i.imm_data.imm.eq(imm)
    yield dut.oper_i.imm_data.imm_ok.eq(imm_ok)
    yield dut.issue_i.eq(1)
    yield
    yield dut.issue_i.eq(0)
    yield
    yield dut.rd.go.eq(1)
    yield from wait_for(dut.rd.rel)
    yield dut.rd.go.eq(0)
    yield from wait_for(dut.wr.rel)
    yield dut.wr.go.eq(1)
    yield from wait_for(dut.busy_o)
    yield
    data = (yield dut.data_o)
    yield dut.wr.go.eq(0)
    yield
    # wait_for(dut.stwd_mem_o)
    return data


def scoreboard_sim(dut):
    # two STs (different addresses)
    yield from store(dut, 4, 3, 2)
    yield from store(dut, 2, 9, 2)
    yield
    # two LDs (deliberately LD from the 1st address then 2nd)
    data = yield from load(dut, 4, 0, 2)
    assert data == 0x0003
    data = yield from load(dut, 2, 0, 2)
    assert data == 0x0009
    yield

    # now do an add
    data = yield from add(dut, 4, 3, 0xfeed)
    assert data == 0x7

    # and an add-immediate
    data = yield from add(dut, 4, 0xdeef, 2, imm_ok=True)
    assert data == 0x6


class TestLDSTCompUnit(LDSTCompUnit):

    def __init__(self, rwid):
        from alu_hier import ALU
        self.alu = alu = ALU(rwid)
        self.mem = mem = TestMemory(rwid, 8)
        LDSTCompUnit.__init__(self, rwid, alu, mem)

    def elaborate(self, platform):
        m = LDSTCompUnit.elaborate(self, platform)
        m.submodules.mem = self.mem
        return m


def test_scoreboard():

    dut = TestLDSTCompUnit(16)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_ldst_comp.il", "w") as f:
        f.write(vl)

    run_simulation(dut, scoreboard_sim(dut), vcd_name='test_ldst_comp.vcd')


if __name__ == '__main__':
    test_scoreboard()
