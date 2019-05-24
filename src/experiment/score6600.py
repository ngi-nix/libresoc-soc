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
from scoreboard.shadow import ShadowMatrix, BranchSpeculationRecord

from compalu import ComputationUnitNoDelay

from alu_hier import ALU, BranchALU
from nmutil.latch import SRLatch

from random import randint


class CompUnits(Elaboratable):

    def __init__(self, rwid, n_units):
        """ Inputs:

            * :rwid:   bit width of register file(s) - both FP and INT
            * :n_units: number of ALUs

            Note: bgt unit is returned so that a shadow unit can be created
            for it

        """
        self.n_units = n_units
        self.rwid = rwid

        # inputs
        self.issue_i = Signal(n_units, reset_less=True)
        self.go_rd_i = Signal(n_units, reset_less=True)
        self.go_wr_i = Signal(n_units, reset_less=True)
        self.shadown_i = Signal(n_units, reset_less=True)
        self.go_die_i = Signal(n_units, reset_less=True)

        # outputs
        self.busy_o = Signal(n_units, reset_less=True)
        self.rd_rel_o = Signal(n_units, reset_less=True)
        self.req_rel_o = Signal(n_units, reset_less=True)

        # in/out register data (note: not register#, actual data)
        self.dest_o = Signal(rwid, reset_less=True)
        self.src1_data_i = Signal(rwid, reset_less=True)
        self.src2_data_i = Signal(rwid, reset_less=True)

        # Branch ALU and CU
        self.bgt = BranchALU(self.rwid)
        self.br1 = ComputationUnitNoDelay(self.rwid, 2, self.bgt)

    def elaborate(self, platform):
        m = Module()

        # Int ALUs
        add = ALU(self.rwid)
        sub = ALU(self.rwid)
        mul = ALU(self.rwid)
        shf = ALU(self.rwid)
        bgt = self.bgt

        m.submodules.comp1 = comp1 = ComputationUnitNoDelay(self.rwid, 2, add)
        m.submodules.comp2 = comp2 = ComputationUnitNoDelay(self.rwid, 2, sub)
        m.submodules.comp3 = comp3 = ComputationUnitNoDelay(self.rwid, 2, mul)
        m.submodules.comp4 = comp4 = ComputationUnitNoDelay(self.rwid, 2, shf)
        m.submodules.br1 = br1 = self.br1
        int_alus = [comp1, comp2, comp3, comp4, br1]

        m.d.comb += comp1.oper_i.eq(Const(0, 2)) # op=add
        m.d.comb += comp2.oper_i.eq(Const(1, 2)) # op=sub
        m.d.comb += comp3.oper_i.eq(Const(2, 2)) # op=mul
        m.d.comb += comp4.oper_i.eq(Const(3, 2)) # op=shf
        m.d.comb += br1.oper_i.eq(Const(0, 2)) # op=bgt

        go_rd_l = []
        go_wr_l = []
        issue_l = []
        busy_l = []
        req_rel_l = []
        rd_rel_l = []
        shadow_l = []
        godie_l = []
        for alu in int_alus:
            req_rel_l.append(alu.req_rel_o)
            rd_rel_l.append(alu.rd_rel_o)
            shadow_l.append(alu.shadown_i)
            godie_l.append(alu.go_die_i)
            go_wr_l.append(alu.go_wr_i)
            go_rd_l.append(alu.go_rd_i)
            issue_l.append(alu.issue_i)
            busy_l.append(alu.busy_o)
        m.d.comb += self.rd_rel_o.eq(Cat(*rd_rel_l))
        m.d.comb += self.req_rel_o.eq(Cat(*req_rel_l))
        m.d.comb += self.busy_o.eq(Cat(*busy_l))
        m.d.comb += Cat(*godie_l).eq(self.go_die_i)
        m.d.comb += Cat(*shadow_l).eq(self.shadown_i)
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

        self.dest_i = Signal(n_regs, reset_less=True) # Dest R# in
        self.src1_i = Signal(n_regs, reset_less=True) # oper1 R# in
        self.src2_i = Signal(n_regs, reset_less=True) # oper2 R# in

        self.g_int_rd_pend_o = Signal(n_regs, reset_less=True)
        self.g_int_wr_pend_o = Signal(n_regs, reset_less=True)

        self.dest_rsel_o = Signal(n_regs, reset_less=True) # dest reg (bot)
        self.src1_rsel_o = Signal(n_regs, reset_less=True) # src1 reg (bot)
        self.src2_rsel_o = Signal(n_regs, reset_less=True) # src2 reg (bot)

        self.req_rel_i = Signal(n_int_alus, reset_less = True)
        self.readable_o = Signal(n_int_alus, reset_less=True)
        self.writable_o = Signal(n_int_alus, reset_less=True)

        self.go_rd_i = Signal(n_int_alus, reset_less=True)
        self.go_wr_i = Signal(n_int_alus, reset_less=True)
        self.req_rel_o = Signal(n_int_alus, reset_less=True)
        self.fn_issue_i = Signal(n_int_alus, reset_less=True)

        # Note: FURegs wr_pend_o is also outputted from here, for use in WaWGrid

    def elaborate(self, platform):
        m = Module()

        n_int_fus = self.n_int_alus

        # Integer FU-FU Dep Matrix
        intfudeps = FUFUDepMatrix(n_int_fus, n_int_fus)
        m.submodules.intfudeps = intfudeps
        # Integer FU-Reg Dep Matrix
        intregdeps = FURegDepMatrix(n_int_fus, self.n_regs)
        m.submodules.intregdeps = intregdeps

        m.d.comb += self.g_int_rd_pend_o.eq(intregdeps.rd_rsel_o)
        m.d.comb += self.g_int_wr_pend_o.eq(intregdeps.wr_rsel_o)

        m.d.comb += intregdeps.rd_pend_i.eq(intregdeps.rd_rsel_o)
        m.d.comb += intregdeps.wr_pend_i.eq(intregdeps.wr_rsel_o)

        m.d.comb += intfudeps.rd_pend_i.eq(intregdeps.rd_pend_o)
        m.d.comb += intfudeps.wr_pend_i.eq(intregdeps.wr_pend_o)
        self.wr_pend_o = intregdeps.wr_pend_o # also output for use in WaWGrid

        m.d.comb += intfudeps.issue_i.eq(self.fn_issue_i)
        m.d.comb += intfudeps.go_rd_i.eq(self.go_rd_i)
        m.d.comb += intfudeps.go_wr_i.eq(self.go_wr_i)
        m.d.comb += self.readable_o.eq(intfudeps.readable_o)
        m.d.comb += self.writable_o.eq(intfudeps.writable_o)

        # Connect function issue / arrays, and dest/src1/src2
        m.d.comb += intregdeps.dest_i.eq(self.dest_i)
        m.d.comb += intregdeps.src1_i.eq(self.src1_i)
        m.d.comb += intregdeps.src2_i.eq(self.src2_i)

        m.d.comb += intregdeps.go_rd_i.eq(self.go_rd_i)
        m.d.comb += intregdeps.go_wr_i.eq(self.go_wr_i)
        m.d.comb += intregdeps.issue_i.eq(self.fn_issue_i)

        m.d.comb += self.dest_rsel_o.eq(intregdeps.dest_rsel_o)
        m.d.comb += self.src1_rsel_o.eq(intregdeps.src1_rsel_o)
        m.d.comb += self.src2_rsel_o.eq(intregdeps.src2_rsel_o)

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
        self.reg_enable_i = Signal(reset_less=True) # enable reg decode

        # outputs
        self.issue_o = Signal(reset_less=True) # instruction was accepted
        self.busy_o = Signal(reset_less=True) # at least one CU is busy

        # for branch speculation experiment.  branch_direction = 0 if
        # the branch hasn't been met yet.  1 indicates "success", 2 is "fail"
        # branch_succ and branch_fail are requests to have the current
        # instruction be dependent on the branch unit "shadow" capability.
        self.branch_succ_i = Signal(reset_less=True)
        self.branch_fail_i = Signal(reset_less=True)
        self.branch_direction_o = Signal(2, reset_less=True)

    def elaborate(self, platform):
        m = Module()

        m.submodules.intregs = self.intregs
        m.submodules.fpregs = self.fpregs

        # dummy values
        m.d.sync += self.branch_succ_i.eq(Const(0))
        m.d.sync += self.branch_fail_i.eq(Const(0))
        m.d.sync += self.branch_direction_o.eq(Const(0))

        # register ports
        int_dest = self.intregs.write_port("dest")
        int_src1 = self.intregs.read_port("src1")
        int_src2 = self.intregs.read_port("src2")

        fp_dest = self.fpregs.write_port("dest")
        fp_src1 = self.fpregs.read_port("src1")
        fp_src2 = self.fpregs.read_port("src2")

        # Int ALUs and Comp Units
        n_int_alus = 5
        m.submodules.cu = cu = CompUnits(self.rwid, n_int_alus)
        m.d.comb += cu.go_die_i.eq(0)
        bgt = cu.bgt # get at the branch computation unit

        # Int FUs
        m.submodules.intfus = intfus = FunctionUnits(self.n_regs, n_int_alus)

        # Count of number of FUs
        n_int_fus = n_int_alus
        n_fp_fus = 0 # for now

        # Integer Priority Picker 1: Adder + Subtractor
        intpick1 = GroupPicker(n_int_fus) # picks between add, sub, mul and shf
        m.submodules.intpick1 = intpick1

        # INT/FP Issue Unit
        regdecode = RegDecode(self.n_regs)
        m.submodules.regdecode = regdecode
        issueunit = IntFPIssueUnit(self.n_regs, n_int_fus, n_fp_fus)
        m.submodules.issueunit = issueunit

        # Shadow Matrix.  currently n_int_fus shadows, to be used for
        # write-after-write hazards.  NOTE: there is one extra for branches,
        # so the shadow width is increased by 1
        m.submodules.shadows = shadows = ShadowMatrix(n_int_fus, n_int_fus+1)

        # combined go_rd/wr + go_die (go_die used to reset latches)
        go_rd_rst = Signal(n_int_fus, reset_less=True)
        go_wr_rst = Signal(n_int_fus, reset_less=True)
        # record previous instruction to cast shadow on current instruction
        fn_issue_prev = Signal(n_int_fus)
        prev_shadow = Signal(n_int_fus)

        # Branch Speculation recorder.  tracks the success/fail state as
        # each instruction is issued, so that when the branch occurs the
        # allow/cancel can be issued as appropriate.
        m.submodules.specrec = bspec = BranchSpeculationRecord(n_int_fus)

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
                     regdecode.enable_i.eq(self.reg_enable_i),
                     issueunit.i.dest_i.eq(regdecode.dest_o),
                     self.issue_o.eq(issueunit.issue_o)
                    ]
        self.int_insn_i = issueunit.i.insn_i # enabled by instruction decode

        # connect global rd/wr pending vector (for WaW detection)
        m.d.sync += issueunit.i.g_wr_pend_i.eq(intfus.g_int_wr_pend_o)
        # TODO: issueunit.f (FP)

        # and int function issue / busy arrays, and dest/src1/src2
        m.d.comb += intfus.dest_i.eq(regdecode.dest_o)
        m.d.comb += intfus.src1_i.eq(regdecode.src1_o)
        m.d.comb += intfus.src2_i.eq(regdecode.src2_o)

        fn_issue_o = issueunit.i.fn_issue_o

        m.d.comb += intfus.fn_issue_i.eq(fn_issue_o)
        m.d.comb += issueunit.i.busy_i.eq(cu.busy_o)
        m.d.comb += self.busy_o.eq(cu.busy_o.bool())

        #---------
        # connect fu-fu matrix
        #---------

        # Group Picker... done manually for now.
        go_rd_o = intpick1.go_rd_o
        go_wr_o = intpick1.go_wr_o
        go_rd_i = intfus.go_rd_i
        go_wr_i = intfus.go_wr_i
        # NOTE: connect to the shadowed versions so that they can "die" (reset)
        m.d.comb += go_rd_i[0:n_int_fus].eq(go_rd_rst[0:n_int_fus]) # rd
        m.d.comb += go_wr_i[0:n_int_fus].eq(go_wr_rst[0:n_int_fus]) # wr

        # Connect Picker
        #---------
        m.d.comb += intpick1.rd_rel_i[0:n_int_fus].eq(cu.rd_rel_o[0:n_int_fus])
        m.d.comb += intpick1.req_rel_i[0:n_int_fus].eq(cu.req_rel_o[0:n_int_fus])
        int_rd_o = intfus.readable_o
        int_wr_o = intfus.writable_o
        m.d.comb += intpick1.readable_i[0:n_int_fus].eq(int_rd_o[0:n_int_fus])
        m.d.comb += intpick1.writable_i[0:n_int_fus].eq(int_wr_o[0:n_int_fus])

        #---------
        # Shadow Matrix
        #---------

        m.d.comb += shadows.issue_i.eq(fn_issue_o)
        # these are explained in ShadowMatrix docstring, and are to be
        # connected to the FUReg and FUFU Matrices, to get them to reset
        # NOTE: do NOT connect these to the Computation Units.  The CUs need to
        # do something slightly different (due to the revolving-door SRLatches)
        m.d.comb += go_rd_rst.eq(go_rd_o | shadows.go_die_o)
        m.d.comb += go_wr_rst.eq(go_wr_o | shadows.go_die_o)

        #---------
        # NOTE; this setup is for the instruction order preservation...

        # connect shadows / go_dies to Computation Units
        m.d.comb += cu.shadown_i[0:n_int_fus].eq(shadows.shadown_o[0:n_int_fus])
        m.d.comb += cu.go_die_i[0:n_int_fus].eq(shadows.go_die_o[0:n_int_fus])

        # ok connect first n_int_fu shadows to busy lines, to create an
        # instruction-order linked-list-like arrangement, using a bit-matrix
        # (instead of e.g. a ring buffer).
        # XXX TODO

        # when written, the shadow can be cancelled (and was good)
        m.d.comb += shadows.s_good_i[0:n_int_fus].eq(go_wr_o[0:n_int_fus])

        # work out the current-activated busy unit (by recording the old one)
        with m.If(fn_issue_o): # only update prev bit if instruction issued
            m.d.sync += fn_issue_prev.eq(fn_issue_o)

        # *previous* instruction shadows *current* instruction, and, obviously,
        # if the previous is completed (!busy) don't cast the shadow!
        m.d.comb += prev_shadow.eq(~fn_issue_o & fn_issue_prev & cu.busy_o)
        for i in range(n_int_fus):
            m.d.comb += shadows.shadow_i[i][0:n_int_fus].eq(prev_shadow)

        #---------
        # ... and this is for branch speculation.  it uses the extra bit
        # tacked onto the ShadowMatrix (hence shadow_wid=n_int_fus+1)
        # only needs to set shadow_i, s_fail_i and s_good_i

        m.d.comb += shadows.s_good_i[n_int_fus].eq(bspec.good_o[i])
        m.d.comb += shadows.s_fail_i[n_int_fus].eq(bspec.fail_o[i])

        with m.If(self.branch_succ_i | self.branch_fail_i):
            for i in range(n_int_fus):
                m.d.comb +=  shadows.shadow_i[i][n_int_fus].eq(1)

        # finally, we need an indicator to the test infrastructure as to
        # whether the branch succeeded or failed, plus, link up to the
        # "recorder" of whether the instruction was under shadow or not

        m.d.comb += bspec.issue_i.eq(fn_issue_o)
        m.d.comb += bspec.good_i.eq(self.branch_succ_i)
        m.d.comb += bspec.fail_i.eq(self.branch_fail_i)
        # branch is active (TODO: a better signal: this is over-using the
        # go_write signal - actually the branch should not be "writing")
        with m.If(cu.br1.go_wr_i):
            m.d.sync += self.branch_direction_o.eq(cu.br1.data_o+Const(1, 2))
            m.d.comb += bspec.branch_i.eq(1)

        #---------
        # Connect Register File(s)
        #---------
        print ("intregdeps wen len", len(intfus.dest_rsel_o))
        m.d.comb += int_dest.wen.eq(intfus.dest_rsel_o)
        m.d.comb += int_src1.ren.eq(intfus.src1_rsel_o)
        m.d.comb += int_src2.ren.eq(intfus.src2_rsel_o)

        # connect ALUs to regfule
        m.d.comb += int_dest.data_i.eq(cu.dest_o)
        m.d.comb += cu.src1_data_i.eq(int_src1.data_o)
        m.d.comb += cu.src2_data_i.eq(int_src2.data_o)

        # connect ALU Computation Units
        m.d.comb += cu.go_rd_i[0:n_int_fus].eq(go_rd_o[0:n_int_fus])
        m.d.comb += cu.go_wr_i[0:n_int_fus].eq(go_wr_o[0:n_int_fus])
        m.d.comb += cu.issue_i[0:n_int_fus].eq(fn_issue_o[0:n_int_fus])

        return m


    def __iter__(self):
        yield from self.intregs
        yield from self.fpregs
        yield self.int_store_i
        yield self.int_dest_i
        yield self.int_src1_i
        yield self.int_src2_i
        yield self.issue_o
        yield self.branch_succ_i
        yield self.branch_fail_i
        yield self.branch_direction_o

    def ports(self):
        return list(self)

IADD = 0
ISUB = 1
IMUL = 2
ISHF = 3
IBGT = 4
IBLT = 5
IBEQ = 6
IBNE = 7

class RegSim:
    def __init__(self, rwidth, nregs):
        self.rwidth = rwidth
        self.regs = [0] * nregs

    def op(self, op, src1, src2, dest):
        maxbits = (1 << self.rwidth) - 1
        src1 = self.regs[src1] & maxbits
        src2 = self.regs[src2] & maxbits
        if op == IADD:
            val = src1 + src2
        elif op == ISUB:
            val = src1 - src2
        elif op == IMUL:
            val = src1 * src2
        elif op == ISHF:
            val = src1 >> (src2 & maxbits)
        elif op == IBGT:
            val = int(src1 > src2)
        elif op == IBLT:
            val = int(src1 < src2)
        elif op == IBEQ:
            val = int(src1 == src2)
        elif op == IBNE:
            val = int(src1 != src2)
        val &= maxbits
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

def int_instr(dut, op, src1, src2, dest, branch_success, branch_fail):
    for i in range(len(dut.int_insn_i)):
        yield dut.int_insn_i[i].eq(0)
    yield dut.int_dest_i.eq(dest)
    yield dut.int_src1_i.eq(src1)
    yield dut.int_src2_i.eq(src2)
    yield dut.int_insn_i[op].eq(1)
    yield dut.reg_enable_i.eq(1)

    # these indicate that the instruction is to be made shadow-dependent on
    # (either) branch success or branch fail
    yield dut.branch_fail_i.eq(branch_fail)
    yield dut.branch_succ_i.eq(branch_success)


def print_reg(dut, rnums):
    rs = []
    for rnum in rnums:
        reg = yield dut.intregs.regs[rnum].reg
        rs.append("%x" % reg)
    rnums = map(str, rnums)
    print ("reg %s: %s" % (','.join(rnums), ','.join(rs)))


def create_random_ops(n_ops, shadowing=False):
    insts = []
    for i in range(n_ops):
        src1 = randint(1, dut.n_regs-1)
        src2 = randint(1, dut.n_regs-1)
        dest = randint(1, dut.n_regs-1)
        op = randint(0, 3)

        if shadowing:
            instrs.append((src1, src2, dest, op, (False, False)))
        else:
            instrs.append((src1, src2, dest, op))
    return insts


def wait_for_busy_clear(dut):
    while True:
        busy_o = yield dut.busy_o
        if not busy_o:
            break
        print ("busy",)
        yield


def wait_for_issue(dut):
    while True:
        issue_o = yield dut.issue_o
        if issue_o:
            for i in range(len(dut.int_insn_i)):
                yield dut.int_insn_i[i].eq(0)
                yield dut.reg_enable_i.eq(0)
            break
        #print ("busy",)
        #yield from print_reg(dut, [1,2,3])
        yield
    #yield from print_reg(dut, [1,2,3])

def scoreboard_branch_sim(dut, alusim):

    yield dut.int_store_i.eq(1)

    for i in range(2):

        # set random values in the registers
        for i in range(1, dut.n_regs):
            val = 31+i*3
            val = randint(0, (1<<alusim.rwidth)-1)
            yield dut.intregs.regs[i].reg.eq(val)
            alusim.setval(i, val)

        # create some instructions: branches create a tree
        insts = create_random_ops(5)

        src1 = randint(1, dut.n_regs-1)
        src2 = randint(1, dut.n_regs-1)
        op = randint(4, 7)

        branch_ok = create_random_ops(5)
        branch_fail = create_random_ops(5)

        insts.append((src1, src2, (branch_ok, branch_fail), op, (0, 0)))

        # issue instruction(s)
        i = -1
        instrs = insts
        branch_direction = 0
        while instrs:
            i += 1
            (src1, src2, dest, op, (shadow_on, shadow_off)) = insts.pop()
            if branch_direction == 1 and shadow_off:
                continue # branch was "success" and this is a "failed"... skip
            if branch_direction == 2 and shadow_on:
                continue # branch was "fail" and this is a "success"... skip
            is_branch = op >= 4
            if is_branch:
                branch_ok, branch_fail = dest
                dest = None
                # ok zip up the branch success / fail instructions and
                # drop them into the queue, one marked "to have branch success"
                # the other to be marked shadow branch "fail".
                # one out of each of these will be cancelled
                for ok, fl in zip(branch_ok, branch_fail):
                    instrs.append((ok[0], ok[1], ok[2], ok[3], (1, 0)))
                    instrs.append((fl[0], fl[1], fl[2], fl[3], (0, 1)))
            print ("instr %d: (%d, %d, %d, %d)" % (i, src1, src2, dest, op))
            yield from int_instr(dut, op, src1, src2, dest,
                  shadow_on, shadow_off)
            yield
            yield from wait_for_issue(dut)
            branch_direction = dut.branch_direction_o # which way branch went

        # wait for all instructions to stop before checking
        yield
        yield from wait_for_busy_clear(dut)

        for (src1, src2, dest, op, (shadow_on, shadow_off)) in insts:
            is_branch = op >= 4
            if is_branch:
                branch_ok, branch_fail = dest
                dest = None
            branch_res = alusim.op(op, src1, src2, dest)
            if is_branch:
                if branch_res:
                    insts.append(branch_ok)
                else:
                    insts.append(branch_fail)

        # check status
        yield from alusim.check(dut)
        yield from alusim.dump(dut)


def scoreboard_sim(dut, alusim):

    yield dut.int_store_i.eq(1)

    for i in range(20):

        # set random values in the registers
        for i in range(1, dut.n_regs):
            val = 31+i*3
            val = randint(0, (1<<alusim.rwidth)-1)
            yield dut.intregs.regs[i].reg.eq(val)
            alusim.setval(i, val)

        # create some instructions (some random, some regression tests)
        instrs = []
        if True:
            for i in range(10):
                src1 = randint(1, dut.n_regs-1)
                src2 = randint(1, dut.n_regs-1)
                while True:
                    dest = randint(1, dut.n_regs-1)
                    break
                    if dest not in [src1, src2]:
                        break
                #src1 = 2
                #src2 = 3
                #dest = 2

                op = randint(0, 4)
                #op = i % 2
                #op = 0

                instrs.append((src1, src2, dest, op))

        if False:
            instrs.append((2, 3, 3, 0))
            instrs.append((5, 3, 3, 1))

        if False:
            instrs.append((5, 6, 2, 1))
            instrs.append((2, 2, 4, 0))
            #instrs.append((2, 2, 3, 1))

        if False:
            instrs.append((2, 1, 2, 3))

        if False:
            instrs.append((2, 6, 2, 1))
            instrs.append((2, 1, 2, 0))

        if False:
            instrs.append((1, 2, 7, 2))
            instrs.append((7, 1, 5, 0))
            instrs.append((4, 4, 1, 1))

        if False:
            instrs.append((5, 6, 2, 2))
            instrs.append((1, 1, 4, 1))
            instrs.append((6, 5, 3, 0))

        if False:
            # Write-after-Write Hazard
            instrs.append( (3, 6, 7, 2) )
            instrs.append( (4, 4, 7, 1) )

        if False:
            # self-read/write-after-write followed by Read-after-Write
            instrs.append((1, 1, 1, 1))
            instrs.append((1, 5, 3, 0))

        if False:
            # Read-after-Write followed by self-read-after-write
            instrs.append((5, 6, 1, 2))
            instrs.append((1, 1, 1, 1))

        if False:
            # self-read-write sandwich
            instrs.append((5, 6, 1, 2))
            instrs.append((1, 1, 1, 1))
            instrs.append((1, 5, 3, 0))

        if False:
            # very weird failure
            instrs.append( (5, 2, 5, 2) )
            instrs.append( (2, 6, 3, 0) )
            instrs.append( (4, 2, 2, 1) )

        # issue instruction(s), wait for issue to be free before proceeding
        for i, (src1, src2, dest, op) in enumerate(instrs):

            print ("instr %d: (%d, %d, %d, %d)" % (i, src1, src2, dest, op))
            alusim.op(op, src1, src2, dest)
            yield from int_instr(dut, op, src1, src2, dest, 0, 0)
            yield
            yield from wait_for_issue(dut)

        # wait for all instructions to stop before checking
        yield
        yield from wait_for_busy_clear(dut)

        # check status
        yield from alusim.check(dut)
        yield from alusim.dump(dut)


def test_scoreboard():
    dut = Scoreboard(16, 8)
    alusim = RegSim(16, 8)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_scoreboard6600.il", "w") as f:
        f.write(vl)

    run_simulation(dut, scoreboard_sim(dut, alusim),
                        vcd_name='test_scoreboard6600.vcd')


if __name__ == '__main__':
    test_scoreboard()
