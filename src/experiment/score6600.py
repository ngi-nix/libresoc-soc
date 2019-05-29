from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Const, Signal, Array, Cat, Elaboratable

from regfile.regfile import RegFileArray, treereduce
from scoreboard.fu_fu_matrix import FUFUDepMatrix
from scoreboard.fu_reg_matrix import FURegDepMatrix
from scoreboard.global_pending import GlobalPending
from scoreboard.group_picker import GroupPicker
from scoreboard.issue_unit import IntFPIssueUnit, RegDecode
from scoreboard.shadow import ShadowMatrix, BranchSpeculationRecord

from compalu import ComputationUnitNoDelay

from alu_hier import ALU, BranchALU
from nmutil.latch import SRLatch

from random import randint, seed
from copy import deepcopy


class CompUnitsBase(Elaboratable):
    """ Computation Unit Base class.

        Amazingly, this class works recursively.  It's supposed to just
        look after some ALUs (that can handle the same operations),
        grouping them together, however it turns out that the same code
        can also group *groups* of Computation Units together as well.
    """
    def __init__(self, rwid, units):
        """ Inputs:

            * :rwid:   bit width of register file(s) - both FP and INT
            * :units: sequence of ALUs (or CompUnitsBase derivatives)
        """
        self.units = units
        self.rwid = rwid
        if units and isinstance(units[0], CompUnitsBase):
            self.n_units = 0
            for u in self.units:
                self.n_units += u.n_units
        else:
            self.n_units = len(units)

        n_units = self.n_units

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
        self.data_o = Signal(rwid, reset_less=True)
        self.src1_i = Signal(rwid, reset_less=True)
        self.src2_i = Signal(rwid, reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        for i, alu in enumerate(self.units):
            print ("elaborate comp%d" % i, self, alu)
            setattr(m.submodules, "comp%d" % i, alu)

        go_rd_l = []
        go_wr_l = []
        issue_l = []
        busy_l = []
        req_rel_l = []
        rd_rel_l = []
        shadow_l = []
        godie_l = []
        for alu in self.units:
            req_rel_l.append(alu.req_rel_o)
            rd_rel_l.append(alu.rd_rel_o)
            shadow_l.append(alu.shadown_i)
            godie_l.append(alu.go_die_i)
            go_wr_l.append(alu.go_wr_i)
            go_rd_l.append(alu.go_rd_i)
            issue_l.append(alu.issue_i)
            busy_l.append(alu.busy_o)
        comb += self.rd_rel_o.eq(Cat(*rd_rel_l))
        comb += self.req_rel_o.eq(Cat(*req_rel_l))
        comb += self.busy_o.eq(Cat(*busy_l))
        comb += Cat(*godie_l).eq(self.go_die_i)
        comb += Cat(*shadow_l).eq(self.shadown_i)
        comb += Cat(*go_wr_l).eq(self.go_wr_i)
        comb += Cat(*go_rd_l).eq(self.go_rd_i)
        comb += Cat(*issue_l).eq(self.issue_i)

        # connect data register input/output

        # merge (OR) all integer FU / ALU outputs to a single value
        # bit of a hack: treereduce needs a list with an item named "data_o"
        if self.units:
            data_o = treereduce(self.units)
            comb += self.data_o.eq(data_o)

        for i, alu in enumerate(self.units):
            comb += alu.src1_i.eq(self.src1_i)
            comb += alu.src2_i.eq(self.src2_i)

        return m


class CompUnitALUs(CompUnitsBase):

    def __init__(self, rwid):
        """ Inputs:

            * :rwid:   bit width of register file(s) - both FP and INT
        """

        # Int ALUs
        add = ALU(rwid)
        sub = ALU(rwid)
        mul = ALU(rwid)
        shf = ALU(rwid)

        units = []
        for alu in [add, sub, mul, shf]:
            units.append(ComputationUnitNoDelay(rwid, 2, alu))

        print ("alu units", units)
        CompUnitsBase.__init__(self, rwid, units)
        print ("alu base init done")

    def elaborate(self, platform):
        print ("alu elaborate start")
        m = CompUnitsBase.elaborate(self, platform)
        print ("alu elaborate done")
        comb = m.d.comb

        comb += self.units[0].oper_i.eq(Const(0, 2)) # op=add
        comb += self.units[1].oper_i.eq(Const(1, 2)) # op=sub
        comb += self.units[2].oper_i.eq(Const(2, 2)) # op=mul
        comb += self.units[3].oper_i.eq(Const(3, 2)) # op=shf

        return m


class CompUnitBR(CompUnitsBase):

    def __init__(self, rwid):
        """ Inputs:

            * :rwid:   bit width of register file(s) - both FP and INT

            Note: bgt unit is returned so that a shadow unit can be created
            for it

        """

        # Branch ALU and CU
        self.bgt = BranchALU(rwid)
        self.br1 = ComputationUnitNoDelay(rwid, 3, self.bgt)
        print ("br units", [self.br1])
        CompUnitsBase.__init__(self, rwid, [self.br1])
        print ("br base init done")

    def elaborate(self, platform):
        print ("br elaborate start")
        m = CompUnitsBase.elaborate(self, platform)
        print ("br elaborate done")
        comb = m.d.comb

        comb += self.br1.oper_i.eq(Const(4, 3)) # op=bgt

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
        self.go_die_i = Signal(n_int_alus, reset_less=True)
        self.req_rel_o = Signal(n_int_alus, reset_less=True)
        self.fn_issue_i = Signal(n_int_alus, reset_less=True)

        # Note: FURegs wr_pend_o is also outputted from here, for use in WaWGrid

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        sync = m.d.sync

        n_int_fus = self.n_int_alus

        # Integer FU-FU Dep Matrix
        intfudeps = FUFUDepMatrix(n_int_fus, n_int_fus)
        m.submodules.intfudeps = intfudeps
        # Integer FU-Reg Dep Matrix
        intregdeps = FURegDepMatrix(n_int_fus, self.n_regs)
        m.submodules.intregdeps = intregdeps

        comb += self.g_int_rd_pend_o.eq(intregdeps.rd_rsel_o)
        comb += self.g_int_wr_pend_o.eq(intregdeps.wr_rsel_o)

        comb += intregdeps.rd_pend_i.eq(intregdeps.rd_rsel_o)
        comb += intregdeps.wr_pend_i.eq(intregdeps.wr_rsel_o)

        comb += intfudeps.rd_pend_i.eq(intregdeps.rd_pend_o)
        comb += intfudeps.wr_pend_i.eq(intregdeps.wr_pend_o)
        self.wr_pend_o = intregdeps.wr_pend_o # also output for use in WaWGrid

        comb += intfudeps.issue_i.eq(self.fn_issue_i)
        comb += intfudeps.go_rd_i.eq(self.go_rd_i)
        comb += intfudeps.go_wr_i.eq(self.go_wr_i)
        comb += intfudeps.go_die_i.eq(self.go_die_i)
        comb += self.readable_o.eq(intfudeps.readable_o)
        comb += self.writable_o.eq(intfudeps.writable_o)

        # Connect function issue / arrays, and dest/src1/src2
        comb += intregdeps.dest_i.eq(self.dest_i)
        comb += intregdeps.src1_i.eq(self.src1_i)
        comb += intregdeps.src2_i.eq(self.src2_i)

        comb += intregdeps.go_rd_i.eq(self.go_rd_i)
        comb += intregdeps.go_wr_i.eq(self.go_wr_i)
        comb += intregdeps.go_die_i.eq(self.go_die_i)
        comb += intregdeps.issue_i.eq(self.fn_issue_i)

        comb += self.dest_rsel_o.eq(intregdeps.dest_rsel_o)
        comb += self.src1_rsel_o.eq(intregdeps.src1_rsel_o)
        comb += self.src2_rsel_o.eq(intregdeps.src2_rsel_o)

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
        comb = m.d.comb
        sync = m.d.sync

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
        n_int_alus = 5
        cua = CompUnitALUs(self.rwid)
        cub = CompUnitBR(self.rwid)
        m.submodules.cu = cu = CompUnitsBase(self.rwid, [cua, cub])
        bgt = cub.bgt # get at the branch computation unit
        br1 = cub.br1

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
        issueunit = IntFPIssueUnit(n_int_fus, n_fp_fus)
        m.submodules.issueunit = issueunit

        # Shadow Matrix.  currently n_int_fus shadows, to be used for
        # write-after-write hazards.  NOTE: there is one extra for branches,
        # so the shadow width is increased by 1
        m.submodules.shadows = shadows = ShadowMatrix(n_int_fus, n_int_fus, True)
        m.submodules.bshadow = bshadow = ShadowMatrix(n_int_fus, 1, False)

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
        comb += [    regdecode.dest_i.eq(self.int_dest_i),
                     regdecode.src1_i.eq(self.int_src1_i),
                     regdecode.src2_i.eq(self.int_src2_i),
                     regdecode.enable_i.eq(self.reg_enable_i),
                     self.issue_o.eq(issueunit.issue_o)
                    ]
        self.int_insn_i = issueunit.i.insn_i # enabled by instruction decode

        # TODO: issueunit.f (FP)

        # and int function issue / busy arrays, and dest/src1/src2
        comb += intfus.dest_i.eq(regdecode.dest_o)
        comb += intfus.src1_i.eq(regdecode.src1_o)
        comb += intfus.src2_i.eq(regdecode.src2_o)

        fn_issue_o = issueunit.i.fn_issue_o

        comb += intfus.fn_issue_i.eq(fn_issue_o)
        comb += issueunit.i.busy_i.eq(cu.busy_o)
        comb += self.busy_o.eq(cu.busy_o.bool())

        #---------
        # merge shadow matrices outputs
        #---------
        
        # these are explained in ShadowMatrix docstring, and are to be
        # connected to the FUReg and FUFU Matrices, to get them to reset
        anydie = Signal(n_int_fus, reset_less=True)
        allshadown = Signal(n_int_fus, reset_less=True)
        shreset = Signal(n_int_fus, reset_less=True)
        comb += allshadown.eq(shadows.shadown_o & bshadow.shadown_o)
        comb += anydie.eq(shadows.go_die_o | bshadow.go_die_o)
        comb += shreset.eq(bspec.match_g_o | bspec.match_f_o)

        #---------
        # connect fu-fu matrix
        #---------

        # Group Picker... done manually for now.
        go_rd_o = intpick1.go_rd_o
        go_wr_o = intpick1.go_wr_o
        go_rd_i = intfus.go_rd_i
        go_wr_i = intfus.go_wr_i
        go_die_i = intfus.go_die_i
        # NOTE: connect to the shadowed versions so that they can "die" (reset)
        comb += go_rd_i[0:n_int_fus].eq(go_rd_o[0:n_int_fus]) # rd
        comb += go_wr_i[0:n_int_fus].eq(go_wr_o[0:n_int_fus]) # wr
        comb += go_die_i[0:n_int_fus].eq(anydie[0:n_int_fus]) # die

        # Connect Picker
        #---------
        comb += intpick1.rd_rel_i[0:n_int_fus].eq(cu.rd_rel_o[0:n_int_fus])
        comb += intpick1.req_rel_i[0:n_int_fus].eq(cu.req_rel_o[0:n_int_fus])
        int_rd_o = intfus.readable_o
        int_wr_o = intfus.writable_o
        comb += intpick1.readable_i[0:n_int_fus].eq(int_rd_o[0:n_int_fus])
        comb += intpick1.writable_i[0:n_int_fus].eq(int_wr_o[0:n_int_fus])

        #---------
        # Shadow Matrix
        #---------

        comb += shadows.issue_i.eq(fn_issue_o)
        #comb += shadows.reset_i[0:n_int_fus].eq(bshadow.go_die_o[0:n_int_fus])
        comb += shadows.reset_i[0:n_int_fus].eq(bshadow.go_die_o[0:n_int_fus])
        #---------
        # NOTE; this setup is for the instruction order preservation...

        # connect shadows / go_dies to Computation Units
        comb += cu.shadown_i[0:n_int_fus].eq(allshadown)
        comb += cu.go_die_i[0:n_int_fus].eq(anydie)

        # ok connect first n_int_fu shadows to busy lines, to create an
        # instruction-order linked-list-like arrangement, using a bit-matrix
        # (instead of e.g. a ring buffer).
        # XXX TODO

        # when written, the shadow can be cancelled (and was good)
        for i in range(n_int_fus):
            comb += shadows.s_good_i[i][0:n_int_fus].eq(go_wr_o[0:n_int_fus])

        # work out the current-activated busy unit (by recording the old one)
        with m.If(fn_issue_o): # only update prev bit if instruction issued
            sync += fn_issue_prev.eq(fn_issue_o)

        # *previous* instruction shadows *current* instruction, and, obviously,
        # if the previous is completed (!busy) don't cast the shadow!
        comb += prev_shadow.eq(~fn_issue_o & cu.busy_o)
        for i in range(n_int_fus):
            comb += shadows.shadow_i[i][0:n_int_fus].eq(prev_shadow)

        #---------
        # ... and this is for branch speculation.  it uses the extra bit
        # tacked onto the ShadowMatrix (hence shadow_wid=n_int_fus+1)
        # only needs to set shadow_i, s_fail_i and s_good_i

        # issue captures shadow_i (if enabled)
        comb += bshadow.reset_i[0:n_int_fus].eq(shreset[0:n_int_fus])

        bactive = Signal(reset_less=True)
        comb += bactive.eq((bspec.active_i | br1.issue_i) & ~br1.go_wr_i)

        # instruction being issued (fn_issue_o) has a shadow cast by the branch
        with m.If(bactive & (self.branch_succ_i | self.branch_fail_i)):
            comb += bshadow.issue_i.eq(fn_issue_o)
            for i in range(n_int_fus):
                with m.If(fn_issue_o & (Const(1<<i))):
                    comb += bshadow.shadow_i[i][0].eq(1)

        # finally, we need an indicator to the test infrastructure as to
        # whether the branch succeeded or failed, plus, link up to the
        # "recorder" of whether the instruction was under shadow or not

        with m.If(br1.issue_i):
            sync += bspec.active_i.eq(1)
        with m.If(self.branch_succ_i):
            comb += bspec.good_i.eq(fn_issue_o & 0x1f)
        with m.If(self.branch_fail_i):
            comb += bspec.fail_i.eq(fn_issue_o & 0x1f)

        # branch is active (TODO: a better signal: this is over-using the
        # go_write signal - actually the branch should not be "writing")
        with m.If(br1.go_wr_i):
            sync += self.branch_direction_o.eq(br1.data_o+Const(1, 2))
            sync += bspec.active_i.eq(0)
            comb += bspec.br_i.eq(1)
            # branch occurs if data == 1, failed if data == 0
            comb += bspec.br_ok_i.eq(br1.data_o == 1)
            for i in range(n_int_fus):
                # *expected* direction of the branch matched against *actual*
                comb += bshadow.s_good_i[i][0].eq(bspec.match_g_o[i])
                # ... or it didn't
                comb += bshadow.s_fail_i[i][0].eq(bspec.match_f_o[i])

        #---------
        # Connect Register File(s)
        #---------
        print ("intregdeps wen len", len(intfus.dest_rsel_o))
        comb += int_dest.wen.eq(intfus.dest_rsel_o)
        comb += int_src1.ren.eq(intfus.src1_rsel_o)
        comb += int_src2.ren.eq(intfus.src2_rsel_o)

        # connect ALUs to regfule
        comb += int_dest.data_i.eq(cu.data_o)
        comb += cu.src1_i.eq(int_src1.data_o)
        comb += cu.src2_i.eq(int_src2.data_o)

        # connect ALU Computation Units
        comb += cu.go_rd_i[0:n_int_fus].eq(go_rd_o[0:n_int_fus])
        comb += cu.go_wr_i[0:n_int_fus].eq(go_wr_o[0:n_int_fus])
        comb += cu.issue_i[0:n_int_fus].eq(fn_issue_o[0:n_int_fus])

        return m


    def __iter__(self):
        yield from self.intregs
        yield from self.fpregs
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
        self.setval(dest, val)
        return val

    def setval(self, dest, val):
        print ("sim setval", dest, hex(val))
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


def create_random_ops(dut, n_ops, shadowing=False, max_opnums=3):
    insts = []
    for i in range(n_ops):
        src1 = randint(1, dut.n_regs-1)
        src2 = randint(1, dut.n_regs-1)
        dest = randint(1, dut.n_regs-1)
        op = randint(0, max_opnums)

        if shadowing:
            insts.append((src1, src2, dest, op, (0, 0)))
        else:
            insts.append((src1, src2, dest, op))
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

    iseed = 3

    for i in range(1):

        print ("rseed", iseed)
        seed(iseed)
        iseed += 1

        yield dut.branch_direction_o.eq(0)

        # set random values in the registers
        for i in range(1, dut.n_regs):
            val = 31+i*3
            val = randint(0, (1<<alusim.rwidth)-1)
            yield dut.intregs.regs[i].reg.eq(val)
            alusim.setval(i, val)

        if False:
            # create some instructions: branches create a tree
            insts = create_random_ops(dut, 1, True, 1)
            #insts.append((6, 6, 1, 2, (0, 0)))
            #insts.append((4, 3, 3, 0, (0, 0)))

            src1 = randint(1, dut.n_regs-1)
            src2 = randint(1, dut.n_regs-1)
            #op = randint(4, 7)
            op = 4 # only BGT at the moment

            branch_ok = create_random_ops(dut, 1, True, 1)
            branch_fail = create_random_ops(dut, 1, True, 1)

            insts.append((src1, src2, (branch_ok, branch_fail), op, (0, 0)))

        if True:
            insts = []
            #insts.append( (3, 5, 2, 0, (0, 0)) )
            branch_ok = []
            branch_fail = []
            branch_ok.append  ( (5, 7, 5, 1, (1, 0)) )
            #branch_ok.append( None )
            branch_fail.append( (1, 1, 2, 0, (0, 1)) )
            #branch_fail.append( None )
            insts.append( (6, 4, (branch_ok, branch_fail), 4, (0, 0)) )

        siminsts = deepcopy(insts)

        # issue instruction(s)
        i = -1
        instrs = insts
        branch_direction = 0
        while instrs:
            yield
            yield
            i += 1
            branch_direction = yield dut.branch_direction_o # way branch went
            (src1, src2, dest, op, (shadow_on, shadow_off)) = insts.pop(0)
            if branch_direction == 1 and shadow_on:
                print ("skip", i, src1, src2, dest, op, shadow_on, shadow_off)
                continue # branch was "success" and this is a "failed"... skip
            if branch_direction == 2 and shadow_off:
                print ("skip", i, src1, src2, dest, op, shadow_on, shadow_off)
                continue # branch was "fail" and this is a "success"... skip
            if branch_direction != 0:
                shadow_on = 0
                shadow_off = 0
            is_branch = op >= 4
            if is_branch:
                branch_ok, branch_fail = dest
                dest = src2
                # ok zip up the branch success / fail instructions and
                # drop them into the queue, one marked "to have branch success"
                # the other to be marked shadow branch "fail".
                # one out of each of these will be cancelled
                for ok, fl in zip(branch_ok, branch_fail):
                    if ok:
                        instrs.append((ok[0], ok[1], ok[2], ok[3], (1, 0)))
                    if fl:
                        instrs.append((fl[0], fl[1], fl[2], fl[3], (0, 1)))
            print ("instr %d: (%d, %d, %d, %d, (%d, %d))" % \
                            (i, src1, src2, dest, op, shadow_on, shadow_off))
            yield from int_instr(dut, op, src1, src2, dest,
                                 shadow_on, shadow_off)
            yield
            yield from wait_for_issue(dut)

        # wait for all instructions to stop before checking
        yield
        yield from wait_for_busy_clear(dut)

        i = -1
        while siminsts:
            instr = siminsts.pop(0)
            if instr is None:
                continue
            (src1, src2, dest, op, (shadow_on, shadow_off)) = instr
            i += 1
            is_branch = op >= 4
            if is_branch:
                branch_ok, branch_fail = dest
                dest = src2
            print ("sim %d: (%d, %d, %d, %d, (%d, %d))" % \
                            (i, src1, src2, dest, op, shadow_on, shadow_off))
            branch_res = alusim.op(op, src1, src2, dest)
            if is_branch:
                if branch_res:
                    siminsts += branch_ok
                else:
                    siminsts += branch_fail

        # check status
        yield from alusim.check(dut)
        yield from alusim.dump(dut)


def scoreboard_sim(dut, alusim):

    seed(0)

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
            instrs = create_random_ops(dut, 10, True, 4)

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

        if False:
            v1 = 4
            yield dut.intregs.regs[5].reg.eq(v1)
            alusim.setval(5, v1)
            yield dut.intregs.regs[3].reg.eq(5)
            alusim.setval(3, 5)
            instrs.append((5, 3, 3, 4, (0, 0)))
            instrs.append((4, 2, 1, 2, (0, 1)))

        if False:
            v1 = 6
            yield dut.intregs.regs[5].reg.eq(v1)
            alusim.setval(5, v1)
            yield dut.intregs.regs[3].reg.eq(5)
            alusim.setval(3, 5)
            instrs.append((5, 3, 3, 4, (0, 0)))
            instrs.append((4, 2, 1, 2, (1, 0)))

        if False:
            instrs.append( (4, 3, 5, 1, (0, 0)) )
            instrs.append( (5, 2, 3, 1, (0, 0)) )
            instrs.append( (7, 1, 5, 2, (0, 0)) )
            instrs.append( (5, 6, 6, 4, (0, 0)) )
            instrs.append( (7, 5, 2, 2, (1, 0)) )
            instrs.append( (1, 7, 5, 0, (0, 1)) )
            instrs.append( (1, 6, 1, 2, (1, 0)) )
            instrs.append( (1, 6, 7, 3, (0, 0)) )
            instrs.append( (6, 7, 7, 0, (0, 0)) )

        # issue instruction(s), wait for issue to be free before proceeding
        for i, (src1, src2, dest, op, (br_ok, br_fail)) in enumerate(instrs):

            print ("instr %d: (%d, %d, %d, %d)" % (i, src1, src2, dest, op))
            alusim.op(op, src1, src2, dest)
            yield from int_instr(dut, op, src1, src2, dest, br_ok, br_fail)
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

    #run_simulation(dut, scoreboard_branch_sim(dut, alusim),
    #                    vcd_name='test_scoreboard6600.vcd')


if __name__ == '__main__':
    test_scoreboard()
