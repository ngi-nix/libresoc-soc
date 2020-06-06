from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Cat, Const, Repl, Elaboratable
from nmigen.lib.coding import Decoder

from nmutil.picker import PriorityPicker


class RegDecode(Elaboratable):
    """ decodes registers into unary

        Inputs

        * :wid:         register file width
    """
    def __init__(self, wid):
        self.reg_width = wid

        # inputs
        self.enable_i = Signal(reset_less=True) # enable decoders
        self.dest_i = Signal(range(wid), reset_less=True) # Dest R# in
        self.src1_i = Signal(range(wid), reset_less=True) # oper1 R# in
        self.src2_i = Signal(range(wid), reset_less=True) # oper2 R# in

        # outputs
        self.dest_o = Signal(wid, reset_less=True) # Dest unary out
        self.src1_o = Signal(wid, reset_less=True) # oper1 unary out
        self.src2_o = Signal(wid, reset_less=True) # oper2 unary out

    def elaborate(self, platform):
        m = Module()
        m.submodules.dest_d = dest_d = Decoder(self.reg_width)
        m.submodules.src1_d = src1_d = Decoder(self.reg_width)
        m.submodules.src2_d = src2_d = Decoder(self.reg_width)

        # dest decoder: write-pending
        for d, i, o in [(dest_d, self.dest_i, self.dest_o),
                     (src1_d, self.src1_i, self.src1_o),
                     (src2_d, self.src2_i, self.src2_o)]:
            m.d.comb += d.i.eq(i)
            m.d.comb += d.n.eq(~self.enable_i)
            m.d.comb += o.eq(d.o)

        return m

    def __iter__(self):
        yield self.enable_i
        yield self.dest_i
        yield self.src1_i
        yield self.src2_i
        yield self.dest_o
        yield self.src1_o
        yield self.src2_o

    def ports(self):
        return list(self)


class IssueUnitGroup(Elaboratable):
    """ Manages a batch of Computation Units all of which can do the same task

        A priority picker will allocate one instruction in this cycle based
        on whether the others are busy.

        insn_i indicates to this module that there is an instruction to be
        issued which this group can handle

        busy_i is a vector of signals that indicate, in this cycle, which
        of the units are currently busy.

        busy_o indicates whether it is "safe to proceed" i.e. whether
        there is a unit here that can *be* issued an instruction

        fn_issue_o indicates, out of the available (non-busy) units,
        which one may be selected
    """
    def __init__(self, n_insns):
        """ Set up inputs and outputs for the Group

            Input Parameters

            * :n_insns:     number of instructions in this issue unit.
        """
        self.n_insns = n_insns

        # inputs
        self.insn_i = Signal(reset_less=True, name="insn_i")
        self.busy_i = Signal(n_insns, reset_less=True, name="busy_i")

        # outputs
        self.fn_issue_o = Signal(n_insns, reset_less=True, name="fn_issue_o")
        self.busy_o = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()

        if self.n_insns == 0:
            return m

        m.submodules.pick = pick = PriorityPicker(self.n_insns)

        # temporaries
        allissue = Signal(self.n_insns, reset_less=True)

        m.d.comb += allissue.eq(Repl(self.insn_i, self.n_insns))
        # Pick one (and only one) of the units to proceed in this cycle
        m.d.comb += pick.i.eq(~self.busy_i & allissue)

        # "Safe to issue" condition is basically when all units are not busy
        m.d.comb += self.busy_o.eq(~((~self.busy_i).bool()))

        # Picker only raises one signal, therefore it's also the fn_issue
        busys = Repl(~self.busy_o, self.n_insns)
        m.d.comb += self.fn_issue_o.eq(pick.o & busys)

        return m

    def __iter__(self):
        yield self.insn_i
        yield self.busy_i
        yield self.fn_issue_o
        yield self.g_issue_o

    def ports(self):
        return list(self)


class IssueUnitArray(Elaboratable):
    """ Convenience module that amalgamates the issue and busy signals

        unit issue_i is to be set externally, at the same time as the
        ALU group oper_i
    """
    def __init__(self, units):
        self.units = units
        self.issue_o = Signal(reset_less=True)
        n_insns = 0
        for u in self.units:
            n_insns += len(u.fn_issue_o)
        self.busy_i = Signal(n_insns, reset_less=True)
        self.fn_issue_o = Signal(n_insns, reset_less=True)
        self.n_insns = n_insns

    def elaborate(self, platform):
        m = Module()
        for i, u in enumerate(self.units):
            setattr(m.submodules, "issue%d" % i, u)

        g_issue_o = []
        busy_i = []
        fn_issue_o = []
        for u in self.units:
            busy_i.append(u.busy_i)
            g_issue_o.append(u.busy_o)
            fn_issue_o.append(u.fn_issue_o)
        m.d.comb += self.issue_o.eq(~(Cat(*g_issue_o).bool()))
        m.d.comb += self.fn_issue_o.eq(Cat(*fn_issue_o))
        m.d.comb += Cat(*busy_i).eq(self.busy_i)

        return m

    def ports(self):
        yield self.busy_i
        yield self.issue_o
        yield self.fn_issue_o
        yield from self.units



class IssueUnit(Elaboratable):
    """ implements 11.4.14 issue unit, p50

        Inputs

        * :n_insns:     number of instructions in this issue unit.
    """
    def __init__(self, n_insns):
        self.n_insns = n_insns

        # inputs
        self.insn_i = Signal(n_insns, reset_less=True, name="insn_i")
        self.busy_i = Signal(n_insns, reset_less=True, name="busy_i")

        # outputs
        self.fn_issue_o = Signal(n_insns, reset_less=True, name="fn_issue_o")
        self.g_issue_o = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()

        if self.n_insns == 0:
            return m

        # temporaries
        fu_stall = Signal(reset_less=True)

        ib_l = []
        for i in range(self.n_insns):
            ib_l.append(self.insn_i[i] & self.busy_i[i])
        m.d.comb += fu_stall.eq(Cat(*ib_l).bool())
        m.d.comb += self.g_issue_o.eq(~(fu_stall))
        for i in range(self.n_insns):
            m.d.comb += self.fn_issue_o[i].eq(self.g_issue_o & self.insn_i[i])

        return m

    def __iter__(self):
        yield self.insn_i
        yield self.busy_i
        yield self.fn_issue_o
        yield self.g_issue_o

    def ports(self):
        return list(self)


class IntFPIssueUnit(Elaboratable):
    def __init__(self, n_int_insns, n_fp_insns):
        self.i = IssueUnit(n_int_insns)
        self.f = IssueUnit(n_fp_insns)
        self.issue_o = Signal(reset_less=True)

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
    yield dut.go_rd_i.eq(1)
    yield
    yield dut.go_rd_i.eq(0)
    yield
    yield dut.go_wr_i.eq(1)
    yield
    yield dut.go_wr_i.eq(0)
    yield

def test_issue_unit():
    dut = IssueUnitGroup(3)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_issue_unit_group.il", "w") as f:
        f.write(vl)

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
