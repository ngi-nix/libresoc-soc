from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Cat, Array, Const, Elaboratable
from nmigen.lib.coding import Decoder

from nmutil.latch import SRLatch, latchregister

from scoreboard.shadow_fn import ShadowFn


class Shadow(Elaboratable):
    """ implements shadowing 11.5.1, p55

        shadowing can be used for branches as well as exceptions (interrupts),
        load/store hold (exceptions again), and vector-element predication
        (once the predicate is known, which it may not be at instruction issue)

        Inputs
        * :shadow_wid:  number of shadow/fail/good/go_die sets

        notes:
        * when shadow_wid = 0, recover and shadown are Consts (i.e. do nothing)
    """
    def __init__(self, shadow_wid=0):
        self.shadow_wid = shadow_wid

        if shadow_wid:
            self.issue_i = Signal(reset_less=True)
            self.shadow_i = Signal(shadow_wid, reset_less=True)
            self.s_fail_i = Signal(shadow_wid, reset_less=True)
            self.s_good_i = Signal(shadow_wid, reset_less=True)
            self.go_die_o = Signal(reset_less=True)
            self.shadown_o = Signal(reset_less=True)
        else:
            self.shadown_o = Const(1)
            self.go_die_o = Const(0)

    def elaborate(self, platform):
        m = Module()
        s_latches = []
        for i in range(self.shadow_wid):
            sh = ShadowFn()
            setattr(m.submodules, "shadow%d" % i, sh)
            s_latches.append(sh)

        # shadow / recover (optional: shadow_wid > 0)
        if self.shadow_wid:
            i_l = []
            fail_l = []
            good_l = []
            shi_l = []
            sho_l = []
            rec_l = []
            # get list of latch signals. really must be a better way to do this
            for l in s_latches:
                i_l.append(l.issue_i)
                shi_l.append(l.shadow_i)
                fail_l.append(l.s_fail_i)
                good_l.append(l.s_good_i)
                sho_l.append(l.shadow_o)
                rec_l.append(l.recover_o)
            m.d.comb += Cat(*i_l).eq(self.issue_i)
            m.d.comb += Cat(*fail_l).eq(self.s_fail_i)
            m.d.comb += Cat(*good_l).eq(self.s_good_i)
            m.d.comb += Cat(*shi_l).eq(self.shadow_i)
            m.d.comb += self.shadown_o.eq(~(Cat(*sho_l).bool()))
            m.d.comb += self.go_die_o.eq(Cat(*rec_l).bool())

        return m

    def __iter__(self):
        if self.shadow_wid:
            yield self.issue_i
            yield self.shadow_i
            yield self.s_fail_i
            yield self.s_good_i
        yield self.go_die_o
        yield self.shadown_o

    def ports(self):
        return list(self)


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
    def __init__(self, n_fus, shadow_wid=0):
        self.n_fus = n_fus
        self.shadow_wid = shadow_wid

        # inputs
        self.issue_i = Signal(n_fus, reset_less=True)
        self.shadow_i = Array(Signal(shadow_wid, name="sh_i", reset_less=True) \
                            for f in range(n_fus))
        self.s_fail_i = Signal(shadow_wid, reset_less=True)
        self.s_good_i = Signal(shadow_wid, reset_less=True)

        # outputs
        self.go_die_o = Signal(n_fus, reset_less=True)
        self.shadown_o = Signal(n_fus, reset_less=True)

    def elaborate(self, platform):
        m = Module()
        shadows = []
        for i in range(self.n_fus):
            sh = Shadow(self.shadow_wid)
            setattr(m.submodules, "sh%d" % i, sh)
            shadows.append(sh)
            # connect shadow/fail/good to all shadows
            m.d.comb += sh.s_fail_i.eq(self.s_fail_i)
            m.d.comb += sh.s_good_i.eq(self.s_good_i)
            # this one is the matrix (shadow enables)
            m.d.comb += sh.shadow_i.eq(self.shadow_i[i])

        # connect all shadow outputs and issue input
        issue_l = []
        sho_l = []
        rec_l = []
        for l in shadows:
            issue_l.append(l.issue_i)
            sho_l.append(l.shadown_o)
            rec_l.append(l.go_die_o)
        m.d.comb += Cat(*issue_l).eq(self.issue_i)
        m.d.comb += self.shadown_o.eq(Cat(*sho_l))
        m.d.comb += self.go_die_o.eq(Cat(*rec_l))

        return m

    def __iter__(self):
        yield self.issue_i
        yield from self.shadow_i
        yield self.s_fail_i
        yield self.s_good_i
        yield self.go_die_o
        yield self.shadown_o

    def ports(self):
        return list(self)


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

    run_simulation(dut, shadow_sim(dut), vcd_name='test_shadow.vcd')

if __name__ == '__main__':
    test_shadow()
