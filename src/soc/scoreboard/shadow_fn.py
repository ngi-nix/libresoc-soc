from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Cat, Repl, Const, Elaboratable
from nmutil.latch import SRLatch


class ShadowFn(Elaboratable):
    """ implements shadowing 11.5.1, p55, just the individual shadow function

        shadowing can be used for branches as well as exceptions (interrupts),
        load/store hold (exceptions again), and vector-element predication
        (once the predicate is known, which it may not be at instruction issue)

        Inputs
        * :shadow_wid:  number of shadow/fail/good/go_die sets

        notes:
        * when shadow_wid = 0, recover and shadown are Consts (i.e. do nothing)
    """
    def __init__(self, slen, syncreset=False):

        self.slen = slen
        self.syncreset = syncreset

        if self.slen:
            # inputs
            self.issue_i = Signal(reset_less=True)
            self.shadow_i  = Signal(slen, reset_less=True)
            self.reset_i  = Signal(reset_less=True)
            self.s_fail_i  = Signal(slen, reset_less=True)
            self.s_good_i  = Signal(slen, reset_less=True)

            # outputs
            self.shadown_o = Signal(reset_less=True)
            self.go_die_o = Signal(reset_less=True)
        else:
            # outputs when no shadowing needed
            self.shadown_o = Const(1)
            self.go_die_o = Const(0)

    def elaborate(self, platform):
        m = Module()
        if self.slen == 0:
            return

        m.submodules.sl = sl = SRLatch(sync=False, llen=self.slen)

        r_ext = Repl(self.reset_i, self.slen)
        reset_r = Signal(self.slen)
        if self.syncreset:
            m.d.comb += reset_r.eq(self.s_good_i | self.s_fail_i | r_ext)
        else:
            m.d.comb += reset_r.eq(self.s_good_i | self.s_fail_i | r_ext)

        i_ext = Repl(self.issue_i, self.slen)
        m.d.comb += sl.s.eq(self.shadow_i & i_ext & \
                            ~self.s_good_i & ~reset_r)
        m.d.comb += sl.r.eq(r_ext | reset_r | self.s_good_i | \
                            (i_ext & ~self.shadow_i))
        m.d.comb += self.go_die_o.eq((sl.qlq & self.s_fail_i).bool())
        m.d.comb += self.shadown_o.eq(~sl.qlq.bool())

        return m

    def __iter__(self):
        yield self.issue_i
        yield self.reset_i
        yield self.shadow_i
        yield self.s_fail_i
        yield self.s_good_i
        yield self.shadown_o
        yield self.go_die_o

    def ports(self):
        return list(self)


def shadow_fn_unit_sim(dut):
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


def test_shadow_fn_unit():
    dut = ShadowFn(4)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_shadow_fn_unit.il", "w") as f:
        f.write(vl)

    run_simulation(dut, shadow_fn_unit_sim(dut),
                   vcd_name='test_shadow_fn_unit.vcd')

if __name__ == '__main__':
    test_shadow_fn_unit()
