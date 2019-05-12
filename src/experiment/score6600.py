from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Const, Signal, Array, Cat, Elaboratable

from regfile.regfile import RegFileArray, treereduce
from scoreboard.fn_unit import IntFnUnit, FPFnUnit, LDFnUnit, STFnUnit
from scoreboard.fu_fu_matrix import FUFUDepMatrix
from scoreboard.fu_reg_matrix import FURegDepMatrix
from scoreboard.global_pending import GlobalPending
from scoreboard.group_picker import GroupPicker
from scoreboard.issue_unit import IntFPIssueUnit, RegDecode

from compalu import ComputationUnitNoDelay

from alu_hier import ALU
from nmutil.latch import SRLatch

from random import randint

class CompUnits(Elaboratable):

    def __init__(self, rwid, n_units):
        """ Inputs:

            * :rwid:   bit width of register file(s) - both FP and INT
            * :n_units: number of ALUs
        """
        self.n_units = n_units
        self.rwid = rwid

        self.issue_i = Signal(n_units, reset_less=True)
        self.go_rd_i = Signal(n_units, reset_less=True)
        self.go_wr_i = Signal(n_units, reset_less=True)
        self.req_rel_o = Signal(n_units, reset_less=True)

        self.dest_o = Signal(rwid, reset_less=True)
        self.src1_data_i = Signal(rwid, reset_less=True)
        self.src2_data_i = Signal(rwid, reset_less=True)

    def elaborate(self, platform):
        m = Module()

        # Int ALUs
        add = ALU(self.rwid)
        sub = ALU(self.rwid)
        m.submodules.comp1 = comp1 = ComputationUnitNoDelay(self.rwid, 1, add)
        m.submodules.comp2 = comp2 = ComputationUnitNoDelay(self.rwid, 1, sub)
        int_alus = [comp1, comp2]

        m.d.comb += comp1.oper_i.eq(Const(0)) # temporary/experiment: op=add
        m.d.comb += comp2.oper_i.eq(Const(1)) # temporary/experiment: op=sub

        go_rd_l = []
        go_wr_l = []
        issue_l = []
        req_rel_l = []
        for alu in int_alus:
            req_rel_l.append(alu.req_rel_o)
            go_wr_l.append(alu.go_wr_i)
            go_rd_l.append(alu.go_rd_i)
            issue_l.append(alu.issue_i)
        m.d.comb += self.req_rel_o.eq(Cat(*req_rel_l))
        m.d.comb += Cat(*go_wr_l).eq(self.go_wr_i)
        m.d.comb += Cat(*go_rd_l).eq(self.go_rd_i)
        m.d.comb += Cat(*issue_l).eq(self.issue_i)

        # connect data register input/output

        # merge (OR) all integer FU / ALU outputs to a single value
        # bit of a hack: treereduce needs a list with an item named "dest_o"
        dest_o = treereduce(int_alus)
        m.d.comb += self.dest_o.eq(dest_o)

        for i, alu in enumerate(int_alus):
            m.d.comb += alu.src1_i.eq(self.src1_data_i)
            m.d.comb += alu.src2_i.eq(self.src2_data_i)

        return m

class FunctionUnits(Elaboratable):

    def __init__(self, n_regs, n_int_alus):
        self.n_regs = n_regs
        self.n_int_alus = n_int_alus

        self.int_dest_i = Signal(max=n_regs, reset_less=True) # Dest R# in
        self.int_src1_i = Signal(max=n_regs, reset_less=True) # oper1 R# in
        self.int_src2_i = Signal(max=n_regs, reset_less=True) # oper2 R# in

        self.req_rel_i = Signal(n_int_alus, reset_less = True)
        self.g_int_rd_pend_o = Signal(n_regs, reset_less=True)
        self.g_int_wr_pend_o = Signal(n_regs, reset_less=True)

        self.go_rd_i = Signal(n_int_alus, reset_less=True)
        self.go_wr_i = Signal(n_int_alus, reset_less=True)
        self.req_rel_o = Signal(n_int_alus, reset_less=True)
        self.fn_issue_i = Signal(n_int_alus, reset_less=True)
        self.fn_busy_o = Signal(n_int_alus, reset_less=True)

    def elaborate(self, platform):
        m = Module()

        # Int FUs
        if_l = []
        int_src1_pend_v = []
        int_src2_pend_v = []
        int_rd_pend_v = []
        int_wr_pend_v = []
        for i in range(self.n_int_alus):
            # set up Integer Function Unit, add to module (and python list)
            fu = IntFnUnit(self.n_regs, shadow_wid=0)
            setattr(m.submodules, "intfu%d" % i, fu)
            if_l.append(fu)
            # collate the read/write pending vectors (to go into global pending)
            int_src1_pend_v.append(fu.src1_pend_o)
            int_src2_pend_v.append(fu.src2_pend_o)
            int_rd_pend_v.append(fu.int_rd_pend_o)
            int_wr_pend_v.append(fu.int_wr_pend_o)
        int_fus = Array(if_l)

        # Global Pending Vectors (INT and TODO FP)
        # NOTE: number of vectors is NOT same as number of FUs.
        g_int_src1_pend_v = GlobalPending(self.n_regs, int_src1_pend_v)
        g_int_src2_pend_v = GlobalPending(self.n_regs, int_src2_pend_v)
        g_int_rd_pend_v = GlobalPending(self.n_regs, int_rd_pend_v)
        g_int_wr_pend_v = GlobalPending(self.n_regs, int_wr_pend_v)
        m.submodules.g_int_src1_pend_v = g_int_src1_pend_v
        m.submodules.g_int_src2_pend_v = g_int_src2_pend_v
        m.submodules.g_int_rd_pend_v = g_int_rd_pend_v
        m.submodules.g_int_wr_pend_v = g_int_wr_pend_v

        m.d.comb += self.g_int_rd_pend_o.eq(g_int_rd_pend_v.g_pend_o)
        m.d.comb += self.g_int_wr_pend_o.eq(g_int_wr_pend_v.g_pend_o)

        # Connect INT Fn Unit global wr/rd pending
        for fu in if_l:
            m.d.comb += fu.g_int_wr_pend_i.eq(g_int_wr_pend_v.g_pend_o)
            m.d.comb += fu.g_int_rd_pend_i.eq(g_int_rd_pend_v.g_pend_o)

        # Connect function issue / busy arrays, and dest/src1/src2
        fn_busy_l = []
        fn_issue_l = []
        req_rel_l = []
        go_rd_l = []
        go_wr_l = []
        for i, fu in enumerate(if_l):
            fn_issue_l.append(fu.issue_i)
            fn_busy_l.append(fu.busy_o)
            go_wr_l.append(fu.go_wr_i)
            go_rd_l.append(fu.go_rd_i)
            req_rel_l.append(fu.req_rel_i)

            m.d.comb += fu.dest_i.eq(self.int_dest_i)
            m.d.comb += fu.src1_i.eq(self.int_src1_i)
            m.d.comb += fu.src2_i.eq(self.int_src2_i)

        m.d.comb += Cat(*req_rel_l).eq(self.req_rel_i)
        m.d.comb += Cat(*fn_issue_l).eq(self.fn_issue_i)
        m.d.comb += self.fn_busy_o.eq(Cat(*fn_busy_l))
        m.d.comb += Cat(*go_wr_l).eq(self.go_wr_i)
        m.d.comb += Cat(*go_rd_l).eq(self.go_rd_i)


        return m


class Scoreboard(Elaboratable):
    def __init__(self, rwid, n_regs):
        """ Inputs:

            * :rwid:   bit width of register file(s) - both FP and INT
            * :n_regs: depth of register file(s) - number of FP and INT regs
        """
        self.rwid = rwid
        self.n_regs = n_regs

        # Register Files
        self.intregs = RegFileArray(rwid, n_regs)
        self.fpregs = RegFileArray(rwid, n_regs)

        # inputs
        self.int_store_i = Signal(reset_less=True) # instruction is a store
        self.int_dest_i = Signal(max=n_regs, reset_less=True) # Dest R# in
        self.int_src1_i = Signal(max=n_regs, reset_less=True) # oper1 R# in
        self.int_src2_i = Signal(max=n_regs, reset_less=True) # oper2 R# in

        self.issue_o = Signal(reset_less=True) # instruction was accepted

    def elaborate(self, platform):
        m = Module()

        m.submodules.intregs = self.intregs
        m.submodules.fpregs = self.fpregs

        # register ports
        int_dest = self.intregs.write_port("dest")
        int_src1 = self.intregs.read_port("src1")
        int_src2 = self.intregs.read_port("src2")

        fp_dest = self.fpregs.write_port("dest")
        fp_src1 = self.fpregs.read_port("src1")
        fp_src2 = self.fpregs.read_port("src2")

        # Int ALUs and Comp Units
        n_int_alus = 2
        m.submodules.cu = cu = CompUnits(self.rwid, n_int_alus)

        # Int FUs
        m.submodules.intfus = intfus = FunctionUnits(self.n_regs, n_int_alus)

        # Count of number of FUs
        n_int_fus = n_int_alus
        n_fp_fus = 0 # for now

        n_fus = n_int_fus + n_fp_fus # plus FP FUs

        # Integer FU-FU Dep Matrix
        intfudeps = FUFUDepMatrix(n_int_fus, n_int_fus)
        m.submodules.intfudeps = intfudeps
        # Integer FU-Reg Dep Matrix
        intregdeps = FURegDepMatrix(n_int_fus, self.n_regs)
        m.submodules.intregdeps = intregdeps

        # Integer Priority Picker 1: Adder + Subtractor
        intpick1 = GroupPicker(2) # picks between add and sub
        m.submodules.intpick1 = intpick1

        # INT/FP Issue Unit
        regdecode = RegDecode(self.n_regs)
        m.submodules.regdecode = regdecode
        issueunit = IntFPIssueUnit(self.n_regs, n_int_fus, n_fp_fus)
        m.submodules.issueunit = issueunit

        #---------
        # ok start wiring things together...
        # "now hear de word of de looord... dem bones dem bones dem dryy bones"
        # https://www.youtube.com/watch?v=pYb8Wm6-QfA
        #---------

        #---------
        # Issue Unit is where it starts.  set up some in/outs for this module
        #---------
        m.d.comb += [issueunit.i.store_i.eq(self.int_store_i),
                     regdecode.dest_i.eq(self.int_dest_i),
                     regdecode.src1_i.eq(self.int_src1_i),
                     regdecode.src2_i.eq(self.int_src2_i),
                     regdecode.enable_i.eq(1),
                     issueunit.i.dest_i.eq(regdecode.dest_o),
                     self.issue_o.eq(issueunit.issue_o)
                    ]
        self.int_insn_i = issueunit.i.insn_i # enabled by instruction decode

        # connect global rd/wr pending vectors
        m.d.comb += issueunit.i.g_wr_pend_i.eq(intfus.g_int_wr_pend_o)
        # TODO: issueunit.f (FP)

        # and int function issue / busy arrays, and dest/src1/src2
        m.d.sync += intfus.int_dest_i.eq(self.int_dest_i)
        m.d.sync += intfus.int_src1_i.eq(self.int_src1_i)
        m.d.sync += intfus.int_src2_i.eq(self.int_src2_i)

        fn_issue_o = Signal(n_int_fus, reset_less=True)
        for i in range(n_int_fus):
            m.d.sync += fn_issue_o[i].eq(issueunit.i.fn_issue_o[i])

        m.d.comb += intfus.fn_issue_i.eq(fn_issue_o)
        # XXX sync, so as to stop a simulation infinite loop
        for i in range(n_int_fus):
            m.d.sync += issueunit.i.busy_i[i].eq(intfus.fn_busy_o[i])

        #---------
        # connect fu-fu matrix
        #---------

        m.d.comb += intfudeps.rd_pend_i.eq(intfus.g_int_rd_pend_o)
        m.d.comb += intfudeps.wr_pend_i.eq(intfus.g_int_wr_pend_o)

        # Group Picker... done manually for now.  TODO: cat array of pick sigs
        go_rd_o = intpick1.go_rd_o
        go_wr_o = intpick1.go_wr_o
        go_rd_i = intfudeps.go_rd_i
        go_wr_i = intfudeps.go_wr_i
        m.d.comb += go_rd_i[0].eq(go_rd_o[0]) # add rd
        m.d.comb += go_wr_i[0].eq(go_wr_o[0]) # add wr

        m.d.comb += go_rd_i[1].eq(go_rd_o[1]) # sub rd
        m.d.comb += go_wr_i[1].eq(go_wr_o[1]) # sub wr

        m.d.comb += intfudeps.issue_i.eq(fn_issue_o)

        # Connect INT FU go_rd/wr
        m.d.comb += intfus.go_rd_i.eq(go_rd_o)
        m.d.comb += intfus.go_wr_i.eq(go_wr_o)

        #---------
        # connect fu-dep matrix
        #---------
        r_go_rd_i = intregdeps.go_rd_i
        r_go_wr_i = intregdeps.go_wr_i
        m.d.comb += r_go_rd_i.eq(go_rd_o)
        m.d.comb += r_go_wr_i.eq(go_wr_o)

        m.d.comb += intregdeps.dest_i.eq(regdecode.dest_o)
        m.d.comb += intregdeps.src1_i.eq(regdecode.src1_o)
        m.d.comb += intregdeps.src2_i.eq(regdecode.src2_o)
        m.d.comb += intregdeps.issue_i.eq(fn_issue_o)

        # Connect Picker
        #---------
        m.d.sync += intpick1.req_rel_i[0].eq(cu.req_rel_o[0])
        m.d.sync += intpick1.req_rel_i[1].eq(cu.req_rel_o[1])
        int_readable_o = intfudeps.readable_o
        int_writable_o = intfudeps.writable_o
        m.d.comb += intpick1.readable_i[0].eq(int_readable_o[0]) # add rd
        m.d.comb += intpick1.writable_i[0].eq(int_writable_o[0]) # add wr
        m.d.comb += intpick1.readable_i[1].eq(int_readable_o[1]) # sub rd
        m.d.comb += intpick1.writable_i[1].eq(int_writable_o[1]) # sub wr

        #---------
        # Connect Register File(s)
        #---------
        print ("intregdeps wen len", len(intregdeps.dest_rsel_o))
        m.d.comb += int_dest.wen.eq(intregdeps.dest_rsel_o)
        m.d.comb += int_src1.ren.eq(intregdeps.src1_rsel_o)
        m.d.comb += int_src2.ren.eq(intregdeps.src2_rsel_o)

        # connect ALUs to regfule
        m.d.comb += int_dest.data_i.eq(cu.dest_o)
        m.d.comb += cu.src1_data_i.eq(int_src1.data_o)
        m.d.comb += cu.src2_data_i.eq(int_src2.data_o)

        # connect ALU Computation Units
        for i in range(n_int_alus):
            m.d.comb += cu.go_rd_i[i].eq(go_rd_o[i])
            m.d.comb += cu.go_wr_i[i].eq(go_wr_o[i])
            m.d.comb += cu.issue_i[i].eq(fn_issue_o[i])

        # Connect ALU request release to FUs
        m.d.sync += intfus.req_rel_i.eq(cu.req_rel_o) # pipe out ready

        return m


    def __iter__(self):
        yield from self.intregs
        yield from self.fpregs
        yield self.int_store_i
        yield self.int_dest_i
        yield self.int_src1_i
        yield self.int_src2_i
        yield self.issue_o
        #yield from self.int_src1
        #yield from self.int_dest
        #yield from self.int_src1
        #yield from self.int_src2
        #yield from self.fp_dest
        #yield from self.fp_src1
        #yield from self.fp_src2

    def ports(self):
        return list(self)

IADD = 0
ISUB = 1

class RegSim:
    def __init__(self, rwidth, nregs):
        self.rwidth = rwidth
        self.regs = [0] * nregs

    def op(self, op, src1, src2, dest):
        src1 = self.regs[src1]
        src2 = self.regs[src2]
        if op == IADD:
            val = (src1 + src2) & ((1<<(self.rwidth))-1)
        elif op == ISUB:
            val = (src1 - src2) & ((1<<(self.rwidth))-1)
        self.regs[dest] = val

    def setval(self, dest, val):
        self.regs[dest] = val

    def dump(self, dut):
        for i, val in enumerate(self.regs):
            reg = yield dut.intregs.regs[i].reg
            okstr = "OK" if reg == val else "!ok"
            print("reg %d expected %x received %x %s" % (i, val, reg, okstr))

    def check(self, dut):
        for i, val in enumerate(self.regs):
            reg = yield dut.intregs.regs[i].reg
            if reg != val:
                print("reg %d expected %x received %x\n" % (i, val, reg))
                yield from self.dump(dut)
                assert False

def int_instr(dut, alusim, op, src1, src2, dest):
    for i in range(len(dut.int_insn_i)):
        yield dut.int_insn_i[i].eq(0)
    yield dut.int_dest_i.eq(dest)
    yield dut.int_src1_i.eq(src1)
    yield dut.int_src2_i.eq(src2)
    yield dut.int_insn_i[op].eq(1)
    alusim.op(op, src1, src2, dest)


def print_reg(dut, rnums):
    rs = []
    for rnum in rnums:
        reg = yield dut.intregs.regs[rnum].reg
        rs.append("%x" % reg)
    rnums = map(str, rnums)
    print ("reg %s: %s" % (','.join(rnums), ','.join(rs)))


def scoreboard_sim(dut, alusim):
    yield dut.int_store_i.eq(0)

    for i in range(1, dut.n_regs):
        yield dut.intregs.regs[i].reg.eq(i*2)
        alusim.setval(i, i*2)

    yield
    yield

    if False:
        yield from int_instr(dut, alusim, IADD, 4, 3, 5)
        yield from print_reg(dut, [3,4,5])
        yield
        yield from int_instr(dut, alusim, IADD, 5, 2, 5)
        yield from print_reg(dut, [3,4,5])
        yield
        yield from int_instr(dut, alusim, ISUB, 5, 1, 3)
        yield from print_reg(dut, [3,4,5])
        yield
        for i in range(len(dut.int_insn_i)):
            yield dut.int_insn_i[i].eq(0)
        yield from print_reg(dut, [3,4,5])
        yield
        yield from print_reg(dut, [3,4,5])
        yield
        yield from print_reg(dut, [3,4,5])
        yield

        yield from alusim.check(dut)

    for i in range(1):
        src1 = randint(1, dut.n_regs-1)
        src2 = randint(1, dut.n_regs-1)
        while True:
            dest = randint(1, dut.n_regs-1)
            break
            if dest not in [src1, src2]:
                break
        src1 = 1
        src2 = 4
        dest = 1

        op = randint(0, 1)
        op = 0
        print ("random %d: %d %d %d %d\n" % (i, op, src1, src2, dest))
        yield from int_instr(dut, alusim, op, src1, src2, dest)
        yield from print_reg(dut, [3,4,5])
        yield
        yield from print_reg(dut, [3,4,5])
        for i in range(len(dut.int_insn_i)):
            yield dut.int_insn_i[i].eq(0)
        yield
        yield
        yield


    yield
    yield from print_reg(dut, [3,4,5])
    yield
    yield from print_reg(dut, [3,4,5])
    yield
    yield
    yield
    yield
    yield from alusim.check(dut)
    yield from alusim.dump(dut)


def explore_groups(dut):
    from nmigen.hdl.ir import Fragment
    from nmigen.hdl.xfrm import LHSGroupAnalyzer

    fragment = dut.elaborate(platform=None)
    fr = Fragment.get(fragment, platform=None)

    groups = LHSGroupAnalyzer()(fragment._statements)

    print (groups)


def test_scoreboard():
    dut = Scoreboard(32, 8)
    alusim = RegSim(32, 8)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_scoreboard6600.il", "w") as f:
        f.write(vl)

    run_simulation(dut, scoreboard_sim(dut, alusim),
                        vcd_name='test_scoreboard6600.vcd')


if __name__ == '__main__':
    test_scoreboard()
