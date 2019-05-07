from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Cat, Elaboratable
from nmutil.latch import SRLatch
from nmigen.lib.coding import Decoder


class ShadowFn(Elaboratable):
    """ implements shadowing 11.5.1, p55, just the individual shadow function
    """
    def __init__(self):

        # inputs
        self.issue_i = Signal(reset_less=True)
        self.shadow_i  = Signal(reset_less=True)
        self.s_fail_i  = Signal(reset_less=True)
        self.s_good_i  = Signal(reset_less=True)

        # outputs
        self.shadow_o = Signal(reset_less=True)
        self.recover_o = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        m.submodules.sl = sl = SRLatch(sync=False)

        m.d.comb += sl.s.eq(self.shadow_i & self.issue_i)
        m.d.comb += sl.r.eq(self.s_good_i)
        m.d.comb += self.recover_o.eq(sl.q & self.s_fail_i)
        m.d.comb += self.shadow_o.eq(sl.q)

        return m

    def __iter__(self):
        yield self.issue_i
        yield self.shadow_i
        yield self.s_fail_i
        yield self.s_good_i
        yield self.shadow_o
        yield self.recover_o

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
    yield dut.go_read_i.eq(1)
    yield
    yield dut.go_read_i.eq(0)
    yield
    yield dut.go_write_i.eq(1)
    yield
    yield dut.go_write_i.eq(0)
    yield


def test_shadow_fn_unit():
    dut = ShadowFn()
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_shadow_fn_unit.il", "w") as f:
        f.write(vl)

    run_simulation(dut, shadow_fn_unit_sim(dut),
                   vcd_name='test_shadow_fn_unit.vcd')

if __name__ == '__main__':
    test_shadow_fn_unit()
