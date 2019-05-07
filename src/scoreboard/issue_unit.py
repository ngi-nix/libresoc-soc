from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Cat, Array, Const, Record, Elaboratable
from nmutil.latch import SRLatch
from nmigen.lib.coding import Decoder

from shadow_fn import ShadowFn


class IssueUnit(Elaboratable):
    """ implements 11.4.14 issue unit, p50

        Inputs

        * :wid:         register file width
        * :n_insns:     number of instructions in this issue unit.
    """
    def __init__(self, wid, n_insns):
        self.reg_width = wid
        self.n_insns = n_insns

        # inputs
        self.store_i = Signal(reset_less=True) # instruction is a store
        self.dest_i = Signal(max=wid, reset_less=True) # Dest R# in 
        self.src1_i = Signal(max=wid, reset_less=True) # oper1 R# in
        self.src2_i = Signal(max=wid, reset_less=True) # oper2 R# in

        self.g_wr_pend_i = Signal(wid, reset_less=True) # write pending vector

        self.insn_i = Array(Signal(reset_less=True, name="insn_i") \
                               for i in range(n_insns))
        self.busy_i = Array(Signal(reset_less=True, name="busy_i") \
                               for i in range(n_insns))

        # outputs
        self.fn_issue_o = Array(Signal(reset_less=True, name="fn_issue_o") \
                               for i in range(n_insns))
        self.g_issue_o = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        m.submodules.dest_d = dest_d = Decoder(self.reg_width)

        # temporaries
        waw_stall = Signal(reset_less=True)
        fu_stall = Signal(reset_less=True)
        pend = Signal(self.reg_width, reset_less=True)

        # dest decoder: write-pending
        m.d.comb += dest_d.i.eq(self.dest_i)
        m.d.comb += dest_d.n.eq(~self.store_i) # decode is inverted
        m.d.comb += pend.eq(dest_d.o & self.g_wr_pend_i)
        m.d.comb += waw_stall.eq(pend.bool())

        ib_l = []
        for i in range(self.n_insns):
            ib_l.append(self.insn_i[i] & self.busy_i[i])
        m.d.comb += fu_stall.eq(Cat(*ib_l).bool())
        m.d.comb += self.g_issue_o.eq(~(waw_stall | fu_stall))
        for i in range(self.n_insns):
            m.d.comb += self.fn_issue_o[i].eq(self.g_issue_o & self.insn_i[i])

        return m

    def __iter__(self):
        yield self.store_i
        yield self.dest_i
        yield self.src1_i
        yield self.src2_i
        yield self.g_wr_pend_i
        yield from self.insn_i
        yield from self.busy_i
        yield from self.fn_issue_o
        yield self.g_issue_o

    def ports(self):
        return list(self)


class IntFPIssueUnit(Elaboratable):
    def __init__(self, wid, n_int_insns, n_fp_insns):
        self.i = IssueUnit(wid, n_int_insns)
        self.f = IssueUnit(wid, n_fp_insns)
        self.issue_o = Signal(reset_less=True)

        # some renames
        self.int_write_pending_i = self.i.g_wr_pend_i
        self.fp_write_pending_i = self.f.g_wr_pend_i
        self.int_write_pending_i.name = 'int_write_pending_i'
        self.fp_write_pending_i.name = 'fp_write_pending_i'

    def elaborate(self, platform):
        m = Module()
        m.submodules.intissue = self.i
        m.submodules.fpissue = self.f

        m.d.comb += self.issue_o.eq(self.i.g_issue_o | self.f.g_issue_o)

        return m

    def ports(self):
        yield self.issue_o
        yield from self.i
        yield from self.f


def issue_unit_sim(dut):
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

def test_issue_unit():
    dut = IssueUnit(32, 3)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_issue_unit.il", "w") as f:
        f.write(vl)

    dut = IntFPIssueUnit(32, 3, 3)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_intfp_issue_unit.il", "w") as f:
        f.write(vl)

    run_simulation(dut, issue_unit_sim(dut), vcd_name='test_issue_unit.vcd')

if __name__ == '__main__':
    test_issue_unit()
