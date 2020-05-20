from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Const, Signal, Array, Cat, Elaboratable

from soc.regfile.regfile import RegFileArray, treereduce
from soc.scoreboard.global_pending import GlobalPending
from soc.scoreboard.group_picker import GroupPicker
from soc.scoreboard.issue_unit import IssueUnitGroup, IssueUnitArray, RegDecode
from soc.scoreboard.shadow import ShadowMatrix, BranchSpeculationRecord
from soc.scoreboard.memfu import MemFunctionUnits
from nmutil.latch import SRLatch
from nmutil.nmoperator import eq

from random import randint, seed
from copy import deepcopy
from math import log
import unittest

# FIXME: fixed up imports
from soc.experiment.score6600 import (IssueToScoreboard, RegSim, instr_q,
                                      wait_for_busy_clear, wait_for_issue, 
                                      CompUnitALUs, CompUnitBR, CompUnitsBase)


class Memory(Elaboratable):
    def __init__(self, regwid, addrw):
        self.ddepth = regwid/8
        depth = (1 << addrw) / self.ddepth
        self.adr = Signal(addrw)
        self.dat_r = Signal(regwid)
        self.dat_w = Signal(regwid)
        self.we = Signal()
        self.mem = Memory(width=regwid, depth=depth, init=range(0, depth))

    def elaborate(self, platform):
        m = Module()
        m.submodules.rdport = rdport = self.mem.read_port()
        m.submodules.wrport = wrport = self.mem.write_port()
        m.d.comb += [
            rdport.addr.eq(self.adr[self.ddepth:]),  # ignore low bits
            self.dat_r.eq(rdport.data),
            wrport.addr.eq(self.adr),
            wrport.data.eq(self.dat_w),
            wrport.en.eq(self.we),
        ]
        return m


class MemSim:
    def __init__(self, regwid, addrw):
        self.regwid = regwid
        self.ddepth = regwid//8
        depth = (1 << addrw) // self.ddepth
        self.mem = list(range(0, depth))

    def ld(self, addr):
        return self.mem[addr >> self.ddepth]

    def st(self, addr, data):
        self.mem[addr >> self.ddepth] = data & ((1 << self.regwid)-1)


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

        # issue q needs to get at these
        self.aluissue = IssueUnitGroup(4)
        self.brissue = IssueUnitGroup(1)
        # and these
        self.alu_oper_i = Signal(4, reset_less=True)
        self.alu_imm_i = Signal(rwid, reset_less=True)
        self.br_oper_i = Signal(4, reset_less=True)
        self.br_imm_i = Signal(rwid, reset_less=True)

        # inputs
        self.int_dest_i = Signal(range(n_regs), reset_less=True)  # Dest R# in
        self.int_src1_i = Signal(range(n_regs), reset_less=True)  # oper1 R# in
        self.int_src2_i = Signal(range(n_regs), reset_less=True)  # oper2 R# in
        self.reg_enable_i = Signal(reset_less=True)  # enable reg decode

        # outputs
        self.issue_o = Signal(reset_less=True)  # instruction was accepted
        self.busy_o = Signal(reset_less=True)  # at least one CU is busy

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
        cua = CompUnitALUs(self.rwid, 3)
        cub = CompUnitBR(self.rwid, 3)
        m.submodules.cu = cu = CompUnitsBase(self.rwid, [cua, cub])
        bgt = cub.bgt  # get at the branch computation unit
        br1 = cub.br1

        # Int FUs
        m.submodules.intfus = intfus = FunctionUnits(self.n_regs, n_int_alus)

        # Count of number of FUs
        n_intfus = n_int_alus
        n_fp_fus = 0  # for now

        # Integer Priority Picker 1: Adder + Subtractor
        intpick1 = GroupPicker(n_intfus)  # picks between add, sub, mul and shf
        m.submodules.intpick1 = intpick1

        # INT/FP Issue Unit
        regdecode = RegDecode(self.n_regs)
        m.submodules.regdecode = regdecode
        issueunit = IssueUnitArray([self.aluissue, self.brissue])
        m.submodules.issueunit = issueunit

        # Shadow Matrix.  currently n_intfus shadows, to be used for
        # write-after-write hazards.  NOTE: there is one extra for branches,
        # so the shadow width is increased by 1
        m.submodules.shadows = shadows = ShadowMatrix(n_intfus, n_intfus, True)
        m.submodules.bshadow = bshadow = ShadowMatrix(n_intfus, 1, False)

        # record previous instruction to cast shadow on current instruction
        prev_shadow = Signal(n_intfus)

        # Branch Speculation recorder.  tracks the success/fail state as
        # each instruction is issued, so that when the branch occurs the
        # allow/cancel can be issued as appropriate.
        m.submodules.specrec = bspec = BranchSpeculationRecord(n_intfus)

        # ---------
        # ok start wiring things together...
        # "now hear de word of de looord... dem bones dem bones dem dryy bones"
        # https://www.youtube.com/watch?v=pYb8Wm6-QfA
        # ---------

        # ---------
        # Issue Unit is where it starts.  set up some in/outs for this module
        # ---------
        comb += [regdecode.dest_i.eq(self.int_dest_i),
                 regdecode.src1_i.eq(self.int_src1_i),
                 regdecode.src2_i.eq(self.int_src2_i),
                 regdecode.enable_i.eq(self.reg_enable_i),
                 self.issue_o.eq(issueunit.issue_o)
                 ]

        # take these to outside (issue needs them)
        comb += cua.oper_i.eq(self.alu_oper_i)
        comb += cua.imm_i.eq(self.alu_imm_i)
        comb += cub.oper_i.eq(self.br_oper_i)
        comb += cub.imm_i.eq(self.br_imm_i)

        # TODO: issueunit.f (FP)

        # and int function issue / busy arrays, and dest/src1/src2
        comb += intfus.dest_i.eq(regdecode.dest_o)
        comb += intfus.src1_i.eq(regdecode.src1_o)
        comb += intfus.src2_i.eq(regdecode.src2_o)

        fn_issue_o = issueunit.fn_issue_o

        comb += intfus.fn_issue_i.eq(fn_issue_o)
        comb += issueunit.busy_i.eq(cu.busy_o)
        comb += self.busy_o.eq(cu.busy_o.bool())

        # ---------
        # merge shadow matrices outputs
        # ---------

        # these are explained in ShadowMatrix docstring, and are to be
        # connected to the FUReg and FUFU Matrices, to get them to reset
        anydie = Signal(n_intfus, reset_less=True)
        allshadown = Signal(n_intfus, reset_less=True)
        shreset = Signal(n_intfus, reset_less=True)
        comb += allshadown.eq(shadows.shadown_o & bshadow.shadown_o)
        comb += anydie.eq(shadows.go_die_o | bshadow.go_die_o)
        comb += shreset.eq(bspec.match_g_o | bspec.match_f_o)

        # ---------
        # connect fu-fu matrix
        # ---------

        # Group Picker... done manually for now.
        go_rd_o = intpick1.go_rd_o
        go_wr_o = intpick1.go_wr_o
        go_rd_i = intfus.go_rd_i
        go_wr_i = intfus.go_wr_i
        go_die_i = intfus.go_die_i
        # NOTE: connect to the shadowed versions so that they can "die" (reset)
        comb += go_rd_i[0:n_intfus].eq(go_rd_o[0:n_intfus])  # rd
        comb += go_wr_i[0:n_intfus].eq(go_wr_o[0:n_intfus])  # wr
        comb += go_die_i[0:n_intfus].eq(anydie[0:n_intfus])  # die

        # Connect Picker
        # ---------
        comb += intpick1.rd_rel_i[0:n_intfus].eq(cu.rd_rel_o[0:n_intfus])
        comb += intpick1.req_rel_i[0:n_intfus].eq(cu.req_rel_o[0:n_intfus])
        int_rd_o = intfus.readable_o
        int_wr_o = intfus.writable_o
        comb += intpick1.readable_i[0:n_intfus].eq(int_rd_o[0:n_intfus])
        comb += intpick1.writable_i[0:n_intfus].eq(int_wr_o[0:n_intfus])

        # ---------
        # Shadow Matrix
        # ---------

        comb += shadows.issue_i.eq(fn_issue_o)
        #comb += shadows.reset_i[0:n_intfus].eq(bshadow.go_die_o[0:n_intfus])
        comb += shadows.reset_i[0:n_intfus].eq(bshadow.go_die_o[0:n_intfus])
        # ---------
        # NOTE; this setup is for the instruction order preservation...

        # connect shadows / go_dies to Computation Units
        comb += cu.shadown_i[0:n_intfus].eq(allshadown)
        comb += cu.go_die_i[0:n_intfus].eq(anydie)

        # ok connect first n_int_fu shadows to busy lines, to create an
        # instruction-order linked-list-like arrangement, using a bit-matrix
        # (instead of e.g. a ring buffer).
        # XXX TODO

        # when written, the shadow can be cancelled (and was good)
        for i in range(n_intfus):
            comb += shadows.s_good_i[i][0:n_intfus].eq(go_wr_o[0:n_intfus])

        # *previous* instruction shadows *current* instruction, and, obviously,
        # if the previous is completed (!busy) don't cast the shadow!
        comb += prev_shadow.eq(~fn_issue_o & cu.busy_o)
        for i in range(n_intfus):
            comb += shadows.shadow_i[i][0:n_intfus].eq(prev_shadow)

        # ---------
        # ... and this is for branch speculation.  it uses the extra bit
        # tacked onto the ShadowMatrix (hence shadow_wid=n_intfus+1)
        # only needs to set shadow_i, s_fail_i and s_good_i

        # issue captures shadow_i (if enabled)
        comb += bshadow.reset_i[0:n_intfus].eq(shreset[0:n_intfus])

        bactive = Signal(reset_less=True)
        comb += bactive.eq((bspec.active_i | br1.issue_i) & ~br1.go_wr_i)

        # instruction being issued (fn_issue_o) has a shadow cast by the branch
        with m.If(bactive & (self.branch_succ_i | self.branch_fail_i)):
            comb += bshadow.issue_i.eq(fn_issue_o)
            for i in range(n_intfus):
                with m.If(fn_issue_o & (Const(1 << i))):
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
            for i in range(n_intfus):
                # *expected* direction of the branch matched against *actual*
                comb += bshadow.s_good_i[i][0].eq(bspec.match_g_o[i])
                # ... or it didn't
                comb += bshadow.s_fail_i[i][0].eq(bspec.match_f_o[i])

        # ---------
        # Connect Register File(s)
        # ---------
        comb += int_dest.wen.eq(intfus.dest_rsel_o)
        comb += int_src1.ren.eq(intfus.src1_rsel_o)
        comb += int_src2.ren.eq(intfus.src2_rsel_o)

        # connect ALUs to regfule
        comb += int_dest.data_i.eq(cu.data_o)
        comb += cu.src1_i.eq(int_src1.data_o)
        comb += cu.src2_i.eq(int_src2.data_o)

        # connect ALU Computation Units
        comb += cu.go_rd_i[0:n_intfus].eq(go_rd_o[0:n_intfus])
        comb += cu.go_wr_i[0:n_intfus].eq(go_wr_o[0:n_intfus])
        comb += cu.issue_i[0:n_intfus].eq(fn_issue_o[0:n_intfus])

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


def int_instr(dut, op, imm, src1, src2, dest, branch_success, branch_fail):
    yield from disable_issue(dut)
    yield dut.int_dest_i.eq(dest)
    yield dut.int_src1_i.eq(src1)
    yield dut.int_src2_i.eq(src2)
    if (op & (0x3 << 2)) != 0:  # branch
        yield dut.brissue.insn_i.eq(1)
        yield dut.br_oper_i.eq(Const(op & 0x3, 2))
        yield dut.br_imm_i.eq(imm)
        dut_issue = dut.brissue
    else:
        yield dut.aluissue.insn_i.eq(1)
        yield dut.alu_oper_i.eq(Const(op & 0x3, 2))
        yield dut.alu_imm_i.eq(imm)
        dut_issue = dut.aluissue
    yield dut.reg_enable_i.eq(1)

    # these indicate that the instruction is to be made shadow-dependent on
    # (either) branch success or branch fail
    yield dut.branch_fail_i.eq(branch_fail)
    yield dut.branch_succ_i.eq(branch_success)

    yield
    yield from wait_for_issue(dut, dut_issue)


def print_reg(dut, rnums):
    rs = []
    for rnum in rnums:
        reg = yield dut.intregs.regs[rnum].reg
        rs.append("%x" % reg)
    rnums = map(str, rnums)
    print("reg %s: %s" % (','.join(rnums), ','.join(rs)))


def create_random_ops(dut, n_ops, shadowing=False, max_opnums=3):
    insts = []
    for i in range(n_ops):
        src1 = randint(1, dut.n_regs-1)
        src2 = randint(1, dut.n_regs-1)
        imm = randint(1, (1 << dut.rwid)-1)
        dest = randint(1, dut.n_regs-1)
        op = randint(0, max_opnums)
        opi = 0 if randint(0, 2) else 1  # set true if random is nonzero

        if shadowing:
            insts.append((src1, src2, dest, op, opi, imm, (0, 0)))
        else:
            insts.append((src1, src2, dest, op, opi, imm))
    return insts


def scoreboard_sim(dut, alusim):

    seed(0)

    for i in range(50):

        # set random values in the registers
        for i in range(1, dut.n_regs):
            val = randint(0, (1 << alusim.rwidth)-1)
            #val = 31+i*3
            #val = i
            yield dut.intregs.regs[i].reg.eq(val)
            alusim.setval(i, val)

        # create some instructions (some random, some regression tests)
        instrs = []
        if True:
            instrs = create_random_ops(dut, 15, True, 4)

        if False:
            instrs.append((1, 2, 2, 1, 1, 20, (0, 0)))

        if False:
            instrs.append((7, 3, 2, 4, (0, 0)))
            instrs.append((7, 6, 6, 2, (0, 0)))
            instrs.append((1, 7, 2, 2, (0, 0)))

        if False:
            instrs.append((2, 3, 3, 0, 0, 0, (0, 0)))
            instrs.append((5, 3, 3, 1, 0, 0, (0, 0)))
            instrs.append((3, 5, 5, 2, 0, 0, (0, 0)))
            instrs.append((5, 3, 3, 3, 0, 0, (0, 0)))
            instrs.append((3, 5, 5, 0, 0, 0, (0, 0)))

        if False:
            instrs.append((3, 3, 4, 0, 0, 13979, (0, 0)))
            instrs.append((6, 4, 1, 2, 0, 40976, (0, 0)))
            instrs.append((1, 4, 7, 4, 1, 23652, (0, 0)))

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
            instrs.append((3, 6, 7, 2))
            instrs.append((4, 4, 7, 1))

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
            instrs.append((5, 2, 5, 2))
            instrs.append((2, 6, 3, 0))
            instrs.append((4, 2, 2, 1))

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
            instrs.append((4, 3, 5, 1, 0, (0, 0)))
            instrs.append((5, 2, 3, 1, 0, (0, 0)))
            instrs.append((7, 1, 5, 2, 0, (0, 0)))
            instrs.append((5, 6, 6, 4, 0, (0, 0)))
            instrs.append((7, 5, 2, 2, 0, (1, 0)))
            instrs.append((1, 7, 5, 0, 0, (0, 1)))
            instrs.append((1, 6, 1, 2, 0, (1, 0)))
            instrs.append((1, 6, 7, 3, 0, (0, 0)))
            instrs.append((6, 7, 7, 0, 0, (0, 0)))

        # issue instruction(s), wait for issue to be free before proceeding
        for i, instr in enumerate(instrs):
            src1, src2, dest, op, opi, imm, (br_ok, br_fail) = instr

            print("instr %d: (%d, %d, %d, %d, %d, %d)" %
                  (i, src1, src2, dest, op, opi, imm))
            alusim.op(op, opi, imm, src1, src2, dest)
            yield from instr_q(dut, op, opi, imm, src1, src2, dest,
                               br_ok, br_fail)

        # wait for all instructions to stop before checking
        while True:
            iqlen = yield dut.qlen_o
            if iqlen == 0:
                break
            yield
        yield
        yield
        yield
        yield
        yield from wait_for_busy_clear(dut)

        # check status
        yield from alusim.check(dut)
        yield from alusim.dump(dut)


@unittest.skip("doesn't work")  # FIXME
def test_scoreboard():
    dut = IssueToScoreboard(2, 1, 1, 16, 8, 8)
    alusim = RegSim(16, 8)
    memsim = MemSim(16, 16)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_scoreboard6600.il", "w") as f:
        f.write(vl)

    run_simulation(dut, scoreboard_sim(dut, alusim),
                   vcd_name='test_scoreboard6600.vcd')

    # run_simulation(dut, scoreboard_branch_sim(dut, alusim),
    #                    vcd_name='test_scoreboard6600.vcd')


def mem_sim(dut):
    yield dut.ld_i.eq(0x1)
    yield dut.fn_issue_i.eq(0x1)
    yield
    yield dut.ld_i.eq(0x0)
    yield dut.st_i.eq(0x3)
    yield dut.fn_issue_i.eq(0x2)
    yield
    yield dut.st_i.eq(0x0)
    yield dut.fn_issue_i.eq(0x0)
    yield

    yield dut.addrs_i[0].eq(0x012)
    yield dut.addrs_i[1].eq(0x012)
    yield dut.addrs_i[2].eq(0x010)
    yield dut.addr_en_i.eq(0x3)
    yield
    # FIXME: addr_we_i is commented out
    # yield dut.addr_we_i.eq(0x3)
    yield
    yield dut.go_ld_i.eq(0x1)
    yield
    yield dut.go_ld_i.eq(0x0)
    yield
    yield dut.go_st_i.eq(0x2)
    yield
    yield dut.go_st_i.eq(0x0)
    yield


def test_mem_fus():
    dut = MemFunctionUnits(8, 11)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_mem2_fus.il", "w") as f:
        f.write(vl)

    run_simulation(dut, mem_sim(dut),
                   vcd_name='test_mem_fus.vcd')


if __name__ == '__main__':
    test_mem_fus()
