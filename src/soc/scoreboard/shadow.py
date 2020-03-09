from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Cat, Array, Const, Elaboratable, Repl
from nmigen.lib.coding import Decoder

from soc.scoreboard.shadow_fn import ShadowFn


class ShadowMatrix(Elaboratable):
    """ Matrix of Shadow Functions.  One per FU.

        Inputs
        * :n_fus:       register file width
        * :shadow_wid:  number of shadow/fail/good/go_die sets

        Notes:

        * Shadow enable/fail/good are all connected to all Shadow Functions
          (incoming at the top)

        * Output is an array of "shadow active" (schroedinger wires: neither
          alive nor dead) and an array of "go die" signals, one per FU.

        * the shadown must be connected to the Computation Unit's
          write release request, preventing it (ANDing) from firing
          (and thus preventing Writable.  this by the way being the
           whole point of having the Shadow Matrix...)

        * go_die_o must be connected to *both* the Computation Unit's
          src-operand and result-operand latch resets, causing both
          of them to reset.

        * go_die_o also needs to be wired into the Dependency and Function
          Unit Matrices by way of over-enabling (ORing) into Go_Read and
          Go_Write, resetting every cell that is required to "die"
    """
    def __init__(self, n_fus, shadow_wid=0, syncreset=False):
        self.syncreset = syncreset
        self.n_fus = n_fus
        self.shadow_wid = shadow_wid

        # inputs
        self.issue_i = Signal(n_fus, reset_less=True)
        self.reset_i = Signal(n_fus, reset_less=True)
        self.shadow_i = Array(Signal(shadow_wid, name="sh_i", reset_less=True) \
                            for f in range(n_fus))
        self.s_fail_i = Array(Signal(shadow_wid, name="fl_i", reset_less=True) \
                            for f in range(n_fus))
        self.s_good_i = Array(Signal(shadow_wid, name="gd_i", reset_less=True) \
                            for f in range(n_fus))
        # outputs
        self.go_die_o = Signal(n_fus, reset_less=True)
        self.shadown_o = Signal(n_fus, reset_less=True)

    def elaborate(self, platform):
        m = Module()
        shadows = []
        for i in range(self.n_fus):
            sh = ShadowFn(self.shadow_wid, self.syncreset)
            setattr(m.submodules, "sh%d" % i, sh)
            shadows.append(sh)
            # connect shadow/fail/good to all shadows
            m.d.comb += sh.s_fail_i.eq(self.s_fail_i[i])
            m.d.comb += sh.s_good_i.eq(self.s_good_i[i])
            # this one is the matrix (shadow enables)
            m.d.comb += sh.shadow_i.eq(self.shadow_i[i])

        # connect all shadow outputs and issue input
        issue_l = []
        reset_l = []
        sho_l = []
        rec_l = []
        for l in shadows:
            issue_l.append(l.issue_i)
            reset_l.append(l.reset_i)
            sho_l.append(l.shadown_o)
            rec_l.append(l.go_die_o)
        m.d.comb += Cat(*issue_l).eq(self.issue_i)
        m.d.comb += Cat(*reset_l).eq(self.reset_i)
        m.d.comb += self.shadown_o.eq(Cat(*sho_l))
        m.d.comb += self.go_die_o.eq(Cat(*rec_l))

        return m

    def __iter__(self):
        yield self.issue_i
        yield self.reset_i
        yield from self.shadow_i
        yield from self.s_fail_i
        yield from self.s_good_i
        yield self.go_die_o
        yield self.shadown_o

    def ports(self):
        return list(self)


class BranchSpeculationRecord(Elaboratable):
    """ A record of which function units will be cancelled and which
        allowed to proceed, on a branch.

        Whilst the input is a pair that says whether the instruction is
        under the "success" branch shadow (good_i) or the "fail" shadow
        (fail_i path), when the branch result is known, the "good" path
        must be cancelled if "fail" occurred, and the "fail" path cancelled
        if "good" occurred.

        therefore, use "good|~fail" and "fail|~good" respectively as
        output.
    """

    def __init__(self, n_fus):
        self.n_fus = n_fus

        # inputs: record *expected* status
        self.active_i = Signal(reset_less=True)
        self.good_i = Signal(n_fus, reset_less=True)
        self.fail_i = Signal(n_fus, reset_less=True)

        # inputs: status of branch (when result was known)
        self.br_i = Signal(reset_less=True)
        self.br_ok_i = Signal(reset_less=True)

        # outputs: true if the *expected* outcome matched the *actual* outcome
        self.match_f_o = Signal(n_fus, reset_less=True)
        self.match_g_o = Signal(n_fus, reset_less=True)

    def elaborate(self, platform):
        m = Module()

        # registers to record *expected* status
        good_r = Signal(self.n_fus)
        fail_r = Signal(self.n_fus)

        for i in range(self.n_fus):
            with m.If(self.active_i):
                m.d.sync += good_r[i].eq(good_r[i] | self.good_i[i])
                m.d.sync += fail_r[i].eq(fail_r[i] | self.fail_i[i])
            with m.If(self.br_i):
                with m.If(good_r[i]):
                    # we expected good, return OK that good was EXPECTED
                    m.d.comb += self.match_g_o[i].eq(self.br_ok_i)
                    m.d.comb += self.match_f_o[i].eq(~self.br_ok_i)
                with m.If(fail_r[i]):
                    # we expected fail, return OK that fail was EXPECTED
                    m.d.comb += self.match_g_o[i].eq(~self.br_ok_i)
                    m.d.comb += self.match_f_o[i].eq(self.br_ok_i)
                m.d.sync += good_r[i].eq(0) # might be set if issue set as well
                m.d.sync += fail_r[i].eq(0) # might be set if issue set as well

        return m

    def __iter__(self):
        yield self.active_i
        yield self.good_i
        yield self.fail_i
        yield self.br_i
        yield self.br_good_i
        yield self.br_fail_i
        yield self.good_o
        yield self.fail_o

    def ports(self):
        return list(self)



class WaWGrid(Elaboratable):
    """ An NxM grid-selector which raises a 2D bit selected by N and M
    """

    def __init__(self, n_fus, shadow_wid):
        self.n_fus = n_fus
        self.shadow_wid = shadow_wid

        self.shadow_i = Signal(shadow_wid, reset_less=True)
        self.fu_i = Signal(n_fus, reset_less=True)

        self.waw_o = Array(Signal(shadow_wid, name="waw_o", reset_less=True) \
                            for f in range(n_fus))

    def elaborate(self, platform):
        m = Module()
        for i in range(self.n_fus):
            v = Repl(self.fu_i[i], self.shadow_wid)
            m.d.comb += self.waw_o[i].eq(v & self.shadow_i)
        return m


def shadow_sim(dut):
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

def test_shadow():
    dut = ShadowMatrix(4, 2)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_shadow.il", "w") as f:
        f.write(vl)

    dut = BranchSpeculationRecord(4)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_branchspecrecord.il", "w") as f:
        f.write(vl)

    run_simulation(dut, shadow_sim(dut), vcd_name='test_shadow.vcd')

if __name__ == '__main__':
    test_shadow()
