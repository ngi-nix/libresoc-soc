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
    dut = Shadow(2)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_shadow.il", "w") as f:
        f.write(vl)

    run_simulation(dut, shadow_sim(dut), vcd_name='test_shadow.vcd')

if __name__ == '__main__':
    test_shadow()
