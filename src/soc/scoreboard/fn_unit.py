from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Cat, Array, Const, Elaboratable
from nmigen.lib.coding import Decoder

from nmutil.latch import SRLatch, latchregister

from soc.scoreboard.shadow import Shadow


class FnUnit(Elaboratable):
    """ implements 11.4.8 function unit, p31
        also implements optional shadowing 11.5.1, p55

        shadowing can be used for branches as well as exceptions (interrupts),
        load/store hold (exceptions again), and vector-element predication
        (once the predicate is known, which it may not be at instruction issue)

        Inputs

        * :wid:         register file width
        * :shadow_wid:  number of shadow/fail/good/go_die sets
        * :n_dests:     number of destination regfile(s) (index: rfile_sel_i)
        * :wr_pend:     if true, writable observes the g_wr_pend_i vector
                        otherwise observes g_rd_pend_i

        notes:

        * dest_i / src1_i / src2_i are in *binary*, whereas...
        * ...g_rd_pend_i / g_wr_pend_i and rd_pend_o / wr_pend_o are UNARY
        * req_rel_i (request release) is the direct equivalent of pipeline
                    "output valid" (valid_o)
        * recover is a local python variable (actually go_die_o)
        * when shadow_wid = 0, recover and shadown are Consts (i.e. do nothing)
        * wr_pend is set False for the majority of uses: however for
          use in a STORE Function Unit it is set to True
    """

    def __init__(self, wid, shadow_wid=0, n_dests=1, wr_pend=False):
        self.reg_width = wid
        self.n_dests = n_dests
        self.shadow_wid = shadow_wid
        self.wr_pend = wr_pend

        # inputs
        if n_dests > 1:
            self.rfile_sel_i = Signal(range(n_dests), reset_less=True)
        else:
            self.rfile_sel_i = Const(0)  # no selection.  gets Array[0]
        self.dest_i = Signal(range(wid), reset_less=True)  # Dest R# in (top)
        self.src1_i = Signal(range(wid), reset_less=True)  # oper1 R# in (top)
        self.src2_i = Signal(range(wid), reset_less=True)  # oper2 R# in (top)
        self.issue_i = Signal(reset_less=True)    # Issue in (top)

        self.go_wr_i = Signal(reset_less=True)  # Go Write in (left)
        self.go_rd_i = Signal(reset_less=True)  # Go Read in (left)
        self.req_rel_i = Signal(reset_less=True)  # request release (left)

        self.g_xx_pend_i = Array(Signal(wid, reset_less=True, name="g_pend_i")
                                 for i in range(n_dests))  # global rd (right)
        self.g_wr_pend_i = Signal(wid, reset_less=True)  # global wr (right)

        if shadow_wid:
            self.shadow_i = Signal(shadow_wid, reset_less=True)
            self.s_fail_i = Signal(shadow_wid, reset_less=True)
            self.s_good_i = Signal(shadow_wid, reset_less=True)
            self.go_die_o = Signal(reset_less=True)

        # outputs
        self.readable_o = Signal(reset_less=True)  # Readable out (right)
        self.writable_o = Array(Signal(reset_less=True, name="writable_o")
                                for i in range(n_dests))  # writable out (right)
        self.busy_o = Signal(reset_less=True)  # busy out (left)

        self.src1_pend_o = Signal(wid, reset_less=True)  # src1 pending
        self.src2_pend_o = Signal(wid, reset_less=True)  # src1 pending
        self.rd_pend_o = Signal(wid, reset_less=True)  # rd pending (right)
        self.xx_pend_o = Array(Signal(wid, reset_less=True, name="pend_o")
                               for i in range(n_dests))  # wr pending (right)

    def elaborate(self, platform):
        m = Module()
        m.submodules.rd_l = rd_l = SRLatch(sync=False)
        m.submodules.wr_l = wr_l = SRLatch(sync=False)
        m.submodules.dest_d = dest_d = Decoder(self.reg_width)
        m.submodules.src1_d = src1_d = Decoder(self.reg_width)
        m.submodules.src2_d = src2_d = Decoder(self.reg_width)

        # shadow / recover (optional: shadow_wid > 0)
        m.submodules.shadow = shadow = Shadow(self.shadow_wid)
        if self.shadow_wid:
            m.d.comb += shadow.issue_i.eq(self.issue_i)
            m.d.comb += shadow.s_fail_i.eq(self.s_fail_i)
            m.d.comb += shadow.s_good_i.eq(self.s_good_i)
            m.d.comb += shadow.shadow_i.eq(self.shadow_i)
        shadown = shadow.shadown_o
        recover = shadow.go_die_o

        # selector
        xx_pend_o = self.xx_pend_o[self.rfile_sel_i]
        writable_o = self.writable_o[self.rfile_sel_i]
        g_pend_i = self.g_xx_pend_i[self.rfile_sel_i]

        for i in range(self.n_dests):
            m.d.comb += self.xx_pend_o[i].eq(0)  # initialise all array
            m.d.comb += self.writable_o[i].eq(0)  # to zero
        m.d.comb += self.readable_o.eq(0)  # to zero

        # go_wr latch: reset on go_wr HI, set on issue
        m.d.comb += wr_l.s.eq(self.issue_i)
        m.d.comb += wr_l.r.eq(self.go_wr_i | recover)

        # src1 latch: reset on go_rd HI, set on issue
        m.d.comb += rd_l.s.eq(self.issue_i)
        m.d.comb += rd_l.r.eq(self.go_rd_i | recover)

        # latch/registers for dest / src1 / src2
        dest_r = Signal(range(self.reg_width), reset_less=True)
        src1_r = Signal(range(self.reg_width), reset_less=True)
        src2_r = Signal(range(self.reg_width), reset_less=True)
        # XXX latch based on *issue* rather than !latch (as in book)
        latchregister(m, self.dest_i, dest_r, self.issue_i)  # wr_l.qn)
        latchregister(m, self.src1_i, src1_r, self.issue_i)  # wr_l.qn)
        latchregister(m, self.src2_i, src2_r, self.issue_i)  # wr_l.qn)

        # dest decoder (use dest reg as input): write-pending out
        m.d.comb += dest_d.i.eq(dest_r)
        m.d.comb += dest_d.n.eq(wr_l.qn)  # decode is inverted
        m.d.comb += self.busy_o.eq(wr_l.q)  # busy if set
        m.d.comb += xx_pend_o.eq(dest_d.o)

        # src1/src2 decoder (use src1/2 regs as input): read-pending out
        m.d.comb += src1_d.i.eq(src1_r)
        m.d.comb += src1_d.n.eq(rd_l.qn)  # decode is inverted
        m.d.comb += src2_d.i.eq(src2_r)
        m.d.comb += src2_d.n.eq(rd_l.qn)  # decode is inverted
        m.d.comb += self.src1_pend_o.eq(src1_d.o)
        m.d.comb += self.src2_pend_o.eq(src2_d.o)
        m.d.comb += self.rd_pend_o.eq(src1_d.o | src2_d.o)

        # readable output signal
        g_rd = Signal(self.reg_width, reset_less=True)
        ro = Signal(reset_less=True)
        m.d.comb += g_rd.eq(~self.g_wr_pend_i & self.rd_pend_o)
        m.d.comb += ro.eq(~g_rd.bool())
        m.d.comb += self.readable_o.eq(ro)

        # writable output signal
        g_wr_v = Signal(self.reg_width, reset_less=True)
        g_wr = Signal(reset_less=True)
        wo = Signal(reset_less=True)
        m.d.comb += g_wr_v.eq(g_pend_i & xx_pend_o)
        m.d.comb += g_wr.eq(~g_wr_v.bool())
        m.d.comb += wo.eq(g_wr & rd_l.qn & self.req_rel_i & shadown)
        m.d.comb += writable_o.eq(wo)

        return m

    def __iter__(self):
        yield self.dest_i
        yield self.src1_i
        yield self.src2_i
        yield self.issue_i
        yield self.go_wr_i
        yield self.go_rd_i
        yield self.req_rel_i
        yield from self.g_xx_pend_i
        yield self.g_wr_pend_i
        yield self.readable_o
        yield from self.writable_o
        yield self.rd_pend_o
        yield from self.xx_pend_o

    def ports(self):
        return list(self)

#############                                     ###############
# ---                                                       --- #
# --- renamed / redirected from base class                  --- #
# ---                                                       --- #
# --- below are convenience classes which match the names   --- #
# --- of the various mitch alsup book chapter gate diagrams --- #
# ---                                                       --- #
#############                                     ###############


class IntFnUnit(FnUnit):
    def __init__(self, wid, shadow_wid=0):
        FnUnit.__init__(self, wid, shadow_wid)
        self.int_rd_pend_o = self.rd_pend_o
        self.int_wr_pend_o = self.xx_pend_o[0]
        self.g_int_wr_pend_i = self.g_wr_pend_i
        self.g_int_rd_pend_i = self.g_xx_pend_i[0]
        self.int_readable_o = self.readable_o
        self.int_writable_o = self.writable_o[0]

        self.int_rd_pend_o.name = "int_rd_pend_o"
        self.int_wr_pend_o.name = "int_wr_pend_o"
        self.g_int_rd_pend_i.name = "g_int_rd_pend_i"
        self.g_int_wr_pend_i.name = "g_int_wr_pend_i"
        self.int_readable_o.name = "int_readable_o"
        self.int_writable_o.name = "int_writable_o"


class FPFnUnit(FnUnit):
    def __init__(self, wid, shadow_wid=0):
        FnUnit.__init__(self, wid, shadow_wid)
        self.fp_rd_pend_o = self.rd_pend_o
        self.fp_wr_pend_o = self.xx_pend_o[0]
        self.g_fp_wr_pend_i = self.g_wr_pend_i
        self.g_fp_rd_pend_i = self.g_xx_pend_i[0]
        self.fp_writable_o = self.writable_o[0]
        self.fp_readable_o = self.readable_o

        self.fp_rd_pend_o.name = "fp_rd_pend_o"
        self.fp_wr_pend_o.name = "fp_wr_pend_o"
        self.g_fp_rd_pend_i.name = "g_fp_rd_pend_i"
        self.g_fp_wr_pend_i.name = "g_fp_wr_pend_i"
        self.fp_writable_o.name = "fp_writable_o"
        self.fp_readable_o.name = "fp_readable_o"


class LDFnUnit(FnUnit):
    """ number of dest selectors: 2. assumes len(int_regfile) == len(fp_regfile)
        * when rfile_sel_i == 0, int_wr_pend_o is set
        * when rfile_sel_i == 1, fp_wr_pend_o is set
    """

    def __init__(self, wid, shadow_wid=0):
        FnUnit.__init__(self, wid, shadow_wid, n_dests=2)
        self.int_rd_pend_o = self.rd_pend_o
        self.int_wr_pend_o = self.xx_pend_o[0]
        self.fp_wr_pend_o = self.xx_pend_o[1]
        self.g_int_wr_pend_i = self.g_wr_pend_i
        self.g_int_rd_pend_i = self.g_xx_pend_i[0]
        self.g_fp_rd_pend_i = self.g_xx_pend_i[1]
        self.int_readable_o = self.readable_o
        self.int_writable_o = self.writable_o[0]
        self.fp_writable_o = self.writable_o[1]

        self.int_rd_pend_o.name = "int_rd_pend_o"
        self.int_wr_pend_o.name = "int_wr_pend_o"
        self.fp_wr_pend_o.name = "fp_wr_pend_o"
        self.g_int_wr_pend_i.name = "g_int_wr_pend_i"
        self.g_int_rd_pend_i.name = "g_int_rd_pend_i"
        self.g_fp_rd_pend_i.name = "g_fp_rd_pend_i"
        self.int_readable_o.name = "int_readable_o"
        self.int_writable_o.name = "int_writable_o"
        self.fp_writable_o.name = "fp_writable_o"


class STFnUnit(FnUnit):
    """ number of dest selectors: 2. assumes len(int_regfile) == len(fp_regfile)
        * wr_pend=False indicates to observe global fp write pending
        * when rfile_sel_i == 0, int_wr_pend_o is set
        * when rfile_sel_i == 1, fp_wr_pend_o is set
        *
    """

    def __init__(self, wid, shadow_wid=0):
        FnUnit.__init__(self, wid, shadow_wid, n_dests=2, wr_pend=True)
        self.int_rd_pend_o = self.rd_pend_o     # 1st int read-pending vector
        self.int2_rd_pend_o = self.xx_pend_o[0]  # 2nd int read-pending vector
        self.fp_rd_pend_o = self.xx_pend_o[1]   # 1x FP read-pending vector
        # yes overwrite FnUnit base class g_wr_pend_i vector
        self.g_int_wr_pend_i = self.g_wr_pend_i = self.g_xx_pend_i[0]
        self.g_fp_wr_pend_i = self.g_xx_pend_i[1]
        self.int_readable_o = self.readable_o
        self.int_writable_o = self.writable_o[0]
        self.fp_writable_o = self.writable_o[1]

        self.int_rd_pend_o.name = "int_rd_pend_o"
        self.int2_rd_pend_o.name = "int2_rd_pend_o"
        self.fp_rd_pend_o.name = "fp_rd_pend_o"
        self.g_int_wr_pend_i.name = "g_int_wr_pend_i"
        self.g_fp_wr_pend_i.name = "g_fp_wr_pend_i"
        self.int_readable_o.name = "int_readable_o"
        self.int_writable_o.name = "int_writable_o"
        self.fp_writable_o.name = "fp_writable_o"


def int_fn_unit_sim(dut):
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
    yield dut.go_rd_i.eq(1)
    yield
    yield dut.go_rd_i.eq(0)
    yield
    yield dut.go_wr_i.eq(1)
    yield
    yield dut.go_wr_i.eq(0)
    yield


def test_int_fn_unit():
    dut = FnUnit(32, 2, 2)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_fn_unit.il", "w") as f:
        f.write(vl)

    dut = LDFnUnit(32, 2)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_ld_fn_unit.il", "w") as f:
        f.write(vl)

    dut = STFnUnit(32, 0)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_st_fn_unit.il", "w") as f:
        f.write(vl)

    run_simulation(dut, int_fn_unit_sim(dut), vcd_name='test_fn_unit.vcd')


if __name__ == '__main__':
    test_int_fn_unit()
