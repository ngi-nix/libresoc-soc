from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Cat, Elaboratable


class PriorityPicker(Elaboratable):
    """ implements a priority-picker.  input: N bits, output: N bits
    """
    def __init__(self, wid):
        self.wid = wid
        # inputs
        self.i = Signal(wid, reset_less=True)
        self.o = Signal(wid, reset_less=True)

    def elaborate(self, platform):
        m = Module()

        res = []
        ni = Signal(self.wid, reset_less = True)
        m.d.comb += ni.eq(~self.i)
        for i in range(0, self.wid):
            t = Signal(reset_less = True)
            res.append(t)
            if i == 0:
                m.d.comb += t.eq(self.i[i])
            else:
                m.d.comb += t.eq(~Cat(ni[i], *self.i[:i]).bool())

        # we like Cat(*xxx).  turn lists into concatenated bits
        m.d.comb += self.o.eq(Cat(*res))

        return m

    def __iter__(self):
        yield self.i
        yield self.o

    def ports(self):
        return list(self)


class GroupPicker(Elaboratable):
    """ implements 10.5 mitch alsup group picker, p27
    """
    def __init__(self, wid):
        self.gp_wid = wid
        # inputs
        self.readable_i = Signal(wid, reset_less=True) # readable in (top)
        self.writable_i = Signal(wid, reset_less=True) # writable in (top)
        self.rd_rel_i = Signal(wid, reset_less=True)   # go read in (top)
        self.req_rel_i = Signal(wid, reset_less=True) # release request in (top)

        # outputs
        self.go_rd_o = Signal(wid, reset_less=True)  # go read (bottom)
        self.go_wr_o = Signal(wid, reset_less=True)  # go write (bottom)

    def elaborate(self, platform):
        m = Module()

        m.submodules.rpick = rpick = PriorityPicker(self.gp_wid)
        m.submodules.wpick = wpick = PriorityPicker(self.gp_wid)

        # combine release (output ready signal) with writeable
        m.d.comb += wpick.i.eq(self.writable_i & self.req_rel_i)
        m.d.comb += self.go_wr_o.eq(wpick.o)

        m.d.comb += rpick.i.eq(self.readable_i & self.rd_rel_i)
        m.d.comb += self.go_rd_o.eq(rpick.o)

        return m

    def __iter__(self):
        yield self.readable_i
        yield self.writable_i
        yield self.req_rel_i
        yield self.go_rd_o
        yield self.go_wr_o

    def ports(self):
        return list(self)


def grp_pick_sim(dut):
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
    yield dut.rd_rel_i.eq(1)
    yield
    yield dut.rd_rel_i.eq(0)
    yield
    yield dut.go_wr_i.eq(1)
    yield
    yield dut.go_wr_i.eq(0)
    yield

def test_grp_pick():
    dut = GroupPicker(4)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_grp_pick.il", "w") as f:
        f.write(vl)

    run_simulation(dut, grp_pick_sim(dut), vcd_name='test_grp_pick.vcd')

if __name__ == '__main__':
    test_grp_pick()
