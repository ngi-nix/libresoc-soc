from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen.hdl.ast import unsigned
from nmigen import Module, Const, Signal, Array, Cat, Elaboratable, Memory
from nmigen.back.pysim import Delay

from soc.regfile.regfile import RegFileArray, ortreereduce
from soc.scoremulti.fu_fu_matrix import FUFUDepMatrix
from soc.scoremulti.fu_reg_matrix import FURegDepMatrix
from soc.scoreboard.global_pending import GlobalPending
from soc.scoreboard.group_picker import GroupPicker
from soc.scoreboard.issue_unit import IssueUnitGroup, IssueUnitArray, RegDecode
from soc.scoreboard.shadow import ShadowMatrix, BranchSpeculationRecord
from soc.scoreboard.instruction_q import Instruction, InstructionQ
from soc.scoreboard.memfu import MemFunctionUnits

from soc.experiment.compalu import ComputationUnitNoDelay
from soc.experiment.compalu_multi import MultiCompUnit, go_record
from soc.experiment.compldst_multi import LDSTCompUnit
from soc.experiment.compldst_multi import CompLDSTOpSubset
from soc.experiment.l0_cache import TstL0CacheBuffer

from soc.experiment.alu_hier import ALU, BranchALU
from soc.fu.alu.alu_input_record import CompALUOpSubset

from openpower.decoder.power_enums import MicrOp, Function
from openpower.decoder.power_decoder import (create_pdecode)
from openpower.decoder.power_decoder2 import (PowerDecode2)
from openpower.decoder.power_decoder2 import Decode2ToExecute1Type

from openpower.simulator.program import Program


from nmutil.latch import SRLatch
from nmutil.nmoperator import eq

from random import randint, seed
from copy import deepcopy
from math import log

from soc.experiment.sim import RegSim, MemSim
from soc.experiment.sim import IADD, ISUB, IMUL, ISHF, IBGT, IBLT, IBEQ, IBNE


class CompUnitsBase(Elaboratable):
    """ Computation Unit Base class.

        Amazingly, this class works recursively.  It's supposed to just
        look after some ALUs (that can handle the same operations),
        grouping them together, however it turns out that the same code
        can also group *groups* of Computation Units together as well.

        Basically it was intended just to concatenate the ALU's issue,
        go_rd etc. signals together, which start out as bits and become
        sequences.  Turns out that the same trick works just as well
        on Computation Units!

        So this class may be used recursively to present a top-level
        sequential concatenation of all the signals in and out of
        ALUs, whilst at the same time making it convenient to group
        ALUs together.

        At the lower level, the intent is that groups of (identical)
        ALUs may be passed the same operation.  Even beyond that,
        the intent is that that group of (identical) ALUs actually
        share the *same pipeline* and as such become a "Concurrent
        Computation Unit" as defined by Mitch Alsup (see section
        11.4.9.3)
    """

    def __init__(self, rwid, units, ldstmode=False):
        """ Inputs:

            * :rwid:   bit width of register file(s) - both FP and INT
            * :units: sequence of ALUs (or CompUnitsBase derivatives)
        """
        self.units = units
        self.ldstmode = ldstmode
        self.rwid = rwid
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
        self.rd0 = go_record(n_units, "rd0")
        self.rd1 = go_record(n_units, "rd1")
        self.go_rd_i = [self.rd0.go, self.rd1.go]  # XXX HACK!
        self.wr0 = go_record(n_units, "wr0")
        self.go_wr_i = [self.wr0.go]
        self.shadown_i = Signal(n_units, reset_less=True)
        self.go_die_i = Signal(n_units, reset_less=True)
        if ldstmode:
            self.go_ad_i = Signal(n_units, reset_less=True)
            self.go_st_i = Signal(n_units, reset_less=True)

        # outputs
        self.busy_o = Signal(n_units, reset_less=True)
        self.rd_rel_o = [self.rd0.rel, self.rd1.rel]  # HACK!
        self.req_rel_o = self.wr0.rel
        self.done_o = Signal(n_units, reset_less=True)
        if ldstmode:
            self.ld_o = Signal(n_units, reset_less=True)  # op is LD
            self.st_o = Signal(n_units, reset_less=True)  # op is ST
            self.adr_rel_o = Signal(n_units, reset_less=True)
            self.sto_rel_o = Signal(n_units, reset_less=True)
            self.load_mem_o = Signal(n_units, reset_less=True)
            self.stwd_mem_o = Signal(n_units, reset_less=True)
            self.addr_o = Signal(rwid, reset_less=True)

        # in/out register data (note: not register#, actual data)
        self.data_o = Signal(rwid, reset_less=True)
        self.src1_i = Signal(rwid, reset_less=True)
        self.src2_i = Signal(rwid, reset_less=True)
        # input operand

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        for i, alu in enumerate(self.units):
            setattr(m.submodules, "comp%d" % i, alu)

        go_rd_l0 = []
        go_rd_l1 = []
        go_wr_l = []
        issue_l = []
        busy_l = []
        req_rel_l = []
        done_l = []
        rd_rel0_l = []
        rd_rel1_l = []
        shadow_l = []
        godie_l = []
        for alu in self.units:
            req_rel_l.append(alu.req_rel_o)
            done_l.append(alu.done_o)
            shadow_l.append(alu.shadown_i)
            godie_l.append(alu.go_die_i)
            print(alu, "rel", alu.req_rel_o, alu.rd_rel_o)
            rd_rel0_l.append(alu.rd_rel_o[0])
            rd_rel1_l.append(alu.rd_rel_o[1])
            go_wr_l.append(alu.go_wr_i)
            go_rd_l0.append(alu.go_rd_i[0])
            go_rd_l1.append(alu.go_rd_i[1])
            issue_l.append(alu.issue_i)
            busy_l.append(alu.busy_o)
        comb += self.rd0.rel.eq(Cat(*rd_rel0_l))
        comb += self.rd1.rel.eq(Cat(*rd_rel1_l))
        comb += self.req_rel_o.eq(Cat(*req_rel_l))
        comb += self.done_o.eq(Cat(*done_l))
        comb += self.busy_o.eq(Cat(*busy_l))
        comb += Cat(*godie_l).eq(self.go_die_i)
        comb += Cat(*shadow_l).eq(self.shadown_i)
        comb += Cat(*go_wr_l).eq(self.wr0.go)  # XXX TODO
        comb += Cat(*go_rd_l0).eq(self.rd0.go)
        comb += Cat(*go_rd_l1).eq(self.rd1.go)
        comb += Cat(*issue_l).eq(self.issue_i)

        # connect data register input/output

        # merge (OR) all integer FU / ALU outputs to a single value
        # XXX NOTE: this only works because there is a single "port"
        # protected by a single go_wr.  multi-issue requires a bus
        # to be inserted here.
        if self.units:
            data_o = ortreereduce(self.units, "data_o")
            comb += self.data_o.eq(data_o)
            if self.ldstmode:
                addr_o = ortreereduce(self.units, "addr_o")
                comb += self.addr_o.eq(addr_o)

        for i, alu in enumerate(self.units):
            comb += alu.src1_i.eq(self.src1_i)
            comb += alu.src2_i.eq(self.src2_i)

        if not self.ldstmode:
            return m

        ldmem_l = []
        stmem_l = []
        go_ad_l = []
        go_st_l = []
        ld_l = []
        st_l = []
        adr_rel_l = []
        sto_rel_l = []
        for alu in self.units:
            ld_l.append(alu.ld_o)
            st_l.append(alu.st_o)
            adr_rel_l.append(alu.adr_rel_o)
            sto_rel_l.append(alu.sto_rel_o)
            ldmem_l.append(alu.load_mem_o)
            stmem_l.append(alu.stwd_mem_o)
            go_ad_l.append(alu.go_ad_i)
            go_st_l.append(alu.go_st_i)
        comb += self.ld_o.eq(Cat(*ld_l))
        comb += self.st_o.eq(Cat(*st_l))
        comb += self.adr_rel_o.eq(Cat(*adr_rel_l))
        comb += self.sto_rel_o.eq(Cat(*sto_rel_l))
        comb += self.load_mem_o.eq(Cat(*ldmem_l))
        comb += self.stwd_mem_o.eq(Cat(*stmem_l))
        comb += Cat(*go_ad_l).eq(self.go_ad_i)
        comb += Cat(*go_st_l).eq(self.go_st_i)

        return m


class CompUnitLDSTs(CompUnitsBase):

    def __init__(self, rwid, opwid, n_ldsts, l0):
        """ Inputs:

            * :rwid:   bit width of register file(s) - both FP and INT
            * :opwid:  operand bit width
        """
        self.opwid = opwid

        # inputs
        self.op = CompLDSTOpSubset("cul_i")

        # LD/ST Units
        units = []
        for i in range(n_ldsts):
            pi = l0.l0.dports[i].pi
            units.append(LDSTCompUnit(pi, rwid, awid=48))

        CompUnitsBase.__init__(self, rwid, units, ldstmode=True)

    def elaborate(self, platform):
        m = CompUnitsBase.elaborate(self, platform)
        comb = m.d.comb

        # hand the same operation to all units
        for ldst in self.units:
            comb += ldst.oper_i.eq(self.op)

        return m


class CompUnitALUs(CompUnitsBase):

    def __init__(self, rwid, opwid, n_alus):
        """ Inputs:

            * :rwid:   bit width of register file(s) - both FP and INT
            * :opwid:  operand bit width
        """
        self.opwid = opwid

        # inputs
        self.op = CompALUOpSubset("cua_i")

        # Int ALUs
        alus = []
        for i in range(n_alus):
            alus.append(ALU(rwid))

        units = []
        for alu in alus:
            aluopwid = 3  # extra bit for immediate mode
            units.append(MultiCompUnit(rwid, alu, CompALUOpSubset))

        CompUnitsBase.__init__(self, rwid, units)

    def elaborate(self, platform):
        m = CompUnitsBase.elaborate(self, platform)
        comb = m.d.comb

        # hand the subset of operation to ALUs
        for alu in self.units:
            comb += alu.oper_i.eq(self.op)

        return m


class CompUnitBR(CompUnitsBase):

    def __init__(self, rwid, opwid):
        """ Inputs:

            * :rwid:   bit width of register file(s) - both FP and INT
            * :opwid:  operand bit width

            Note: bgt unit is returned so that a shadow unit can be created
            for it
        """
        self.opwid = opwid

        # inputs
        self.op = CompALUOpSubset("cua_i")  # TODO - CompALUBranchSubset
        self.oper_i = Signal(opwid, reset_less=True)
        self.imm_i = Signal(rwid, reset_less=True)

        # Branch ALU and CU
        self.bgt = BranchALU(rwid)
        aluopwid = 3  # extra bit for immediate mode
        self.br1 = MultiCompUnit(rwid, self.bgt, CompALUOpSubset)
        CompUnitsBase.__init__(self, rwid, [self.br1])

    def elaborate(self, platform):
        m = CompUnitsBase.elaborate(self, platform)
        comb = m.d.comb

        # hand the same operation to all units
        for alu in self.units:
            # comb += alu.oper_i.eq(self.op) # TODO
            comb += alu.oper_i.eq(self.oper_i)
            #comb += alu.imm_i.eq(self.imm_i)

        return m


class FunctionUnits(Elaboratable):

    def __init__(self, n_reg, n_int_alus, n_src, n_dst):
        self.n_src, self.n_dst = n_src, n_dst
        self.n_reg = n_reg
        self.n_int_alus = nf = n_int_alus

        self.g_int_rd_pend_o = Signal(n_reg, reset_less=True)
        self.g_int_wr_pend_o = Signal(n_reg, reset_less=True)

        self.readable_o = Signal(n_int_alus, reset_less=True)
        self.writable_o = Signal(n_int_alus, reset_less=True)

        # arrays
        src = []
        rsel = []
        rd = []
        for i in range(n_src):
            j = i + 1  # name numbering to match src1/src2
            src.append(Signal(n_reg, name="src%d" % j, reset_less=True))
            rsel.append(Signal(n_reg, name="src%d_rsel_o" %
                               j, reset_less=True))
            rd.append(Signal(nf, name="gord%d_i" % j, reset_less=True))
        dst = []
        dsel = []
        wr = []
        for i in range(n_dst):
            j = i + 1  # name numbering to match src1/src2
            dst.append(Signal(n_reg, name="dst%d" % j, reset_less=True))
            dsel.append(Signal(n_reg, name="dst%d_rsel_o" %
                               j, reset_less=True))
            wr.append(Signal(nf, name="gowr%d_i" % j, reset_less=True))
        wpnd = []
        pend = []
        for i in range(nf):
            j = i + 1  # name numbering to match src1/src2
            pend.append(Signal(nf, name="rd_src%d_pend_o" %
                               j, reset_less=True))
            wpnd.append(Signal(nf, name="wr_dst%d_pend_o" %
                               j, reset_less=True))

        self.dest_i = Array(dst)     # Dest in (top)
        self.src_i = Array(src)      # oper in (top)

        # for Register File Select Lines (horizontal), per-reg
        self.dst_rsel_o = Array(dsel)  # dest reg (bot)
        self.src_rsel_o = Array(rsel)  # src reg (bot)

        self.go_rd_i = Array(rd)
        self.go_wr_i = Array(wr)

        self.go_die_i = Signal(n_int_alus, reset_less=True)
        self.fn_issue_i = Signal(n_int_alus, reset_less=True)

        # Note: FURegs wr_pend_o is also outputted from here, for use in WaWGrid

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        sync = m.d.sync

        n_intfus = self.n_int_alus

        # Integer FU-FU Dep Matrix
        intfudeps = FUFUDepMatrix(n_intfus, n_intfus, 2, 1)
        m.submodules.intfudeps = intfudeps
        # Integer FU-Reg Dep Matrix
        intregdeps = FURegDepMatrix(n_intfus, self.n_reg, 2, 1)
        m.submodules.intregdeps = intregdeps

        comb += self.g_int_rd_pend_o.eq(intregdeps.v_rd_rsel_o)
        comb += self.g_int_wr_pend_o.eq(intregdeps.v_wr_rsel_o)

        comb += intregdeps.rd_pend_i.eq(intregdeps.v_rd_rsel_o)
        comb += intregdeps.wr_pend_i.eq(intregdeps.v_wr_rsel_o)

        comb += intfudeps.rd_pend_i.eq(intregdeps.rd_pend_o)
        comb += intfudeps.wr_pend_i.eq(intregdeps.wr_pend_o)
        self.wr_pend_o = intregdeps.wr_pend_o  # also output for use in WaWGrid

        comb += intfudeps.issue_i.eq(self.fn_issue_i)
        comb += intfudeps.go_die_i.eq(self.go_die_i)
        comb += self.readable_o.eq(intfudeps.readable_o)
        comb += self.writable_o.eq(intfudeps.writable_o)

        # Connect function issue / arrays, and dest/src1/src2
        for i in range(self.n_src):
            print(i, self.go_rd_i, intfudeps.go_rd_i)
            comb += intfudeps.go_rd_i[i].eq(self.go_rd_i[i])
            comb += intregdeps.src_i[i].eq(self.src_i[i])
            comb += intregdeps.go_rd_i[i].eq(self.go_rd_i[i])
            comb += self.src_rsel_o[i].eq(intregdeps.src_rsel_o[i])
        for i in range(self.n_dst):
            print(i, self.go_wr_i, intfudeps.go_wr_i)
            comb += intfudeps.go_wr_i[i].eq(self.go_wr_i[i])
            comb += intregdeps.dest_i[i].eq(self.dest_i[i])
            comb += intregdeps.go_wr_i[i].eq(self.go_wr_i[i])
            comb += self.dst_rsel_o[i].eq(intregdeps.dest_rsel_o[i])
        comb += intregdeps.go_die_i.eq(self.go_die_i)
        comb += intregdeps.issue_i.eq(self.fn_issue_i)

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

        # Memory (test for now)
        self.l0 = TstL0CacheBuffer()

        # issue q needs to get at these
        self.aluissue = IssueUnitGroup(2)
        self.lsissue = IssueUnitGroup(2)
        self.brissue = IssueUnitGroup(1)
        # and these
        self.instr = Decode2ToExecute1Type("sc_instr")
        self.br_oper_i = Signal(4, reset_less=True)
        self.br_imm_i = Signal(rwid, reset_less=True)
        self.ls_oper_i = Signal(4, reset_less=True)

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
        m.submodules.l0 = l0 = self.l0

        # register ports
        int_dest = self.intregs.write_port("dest")
        int_src1 = self.intregs.read_port("src1")
        int_src2 = self.intregs.read_port("src2")

        fp_dest = self.fpregs.write_port("dest")
        fp_src1 = self.fpregs.read_port("src1")
        fp_src2 = self.fpregs.read_port("src2")

        # Int ALUs and BR ALUs
        n_int_alus = 5
        cua = CompUnitALUs(self.rwid, 3, n_alus=self.aluissue.n_insns)
        cub = CompUnitBR(self.rwid, 3)  # 1 BR ALUs

        # LDST Comp Units
        n_ldsts = 2
        cul = CompUnitLDSTs(self.rwid, 4, self.lsissue.n_insns, l0)

        # Comp Units
        m.submodules.cu = cu = CompUnitsBase(self.rwid, [cua, cul, cub])
        bgt = cub.bgt  # get at the branch computation unit
        br1 = cub.br1

        # Int FUs
        fu_n_src = 2
        fu_n_dst = 1
        m.submodules.intfus = intfus = FunctionUnits(self.n_regs, n_int_alus,
                                                     fu_n_src, fu_n_dst)

        # Memory FUs
        m.submodules.memfus = memfus = MemFunctionUnits(n_ldsts, 5)

        # Memory Priority Picker 1: one gateway per memory port
        # picks 1 reader and 1 writer to intreg
        mempick1 = GroupPicker(n_ldsts, 1, 1)
        m.submodules.mempick1 = mempick1

        # Count of number of FUs
        n_intfus = n_int_alus
        n_fp_fus = 0  # for now

        # Integer Priority Picker 1: Adder + Subtractor (and LD/ST)
        # picks 1 reader and 1 writer to intreg
        ipick1 = GroupPicker(n_intfus, fu_n_src, fu_n_dst)
        m.submodules.intpick1 = ipick1

        # INT/FP Issue Unit
        regdecode = RegDecode(self.n_regs)
        m.submodules.regdecode = regdecode
        issueunit = IssueUnitArray([self.aluissue, self.lsissue, self.brissue])
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
        comb += cua.op.eq_from_execute1(self.instr)
        comb += cub.oper_i.eq(self.br_oper_i)
        comb += cub.imm_i.eq(self.br_imm_i)
        comb += cul.op.eq_from_execute1(self.instr)

        # TODO: issueunit.f (FP)

        # and int function issue / busy arrays, and dest/src1/src2
        comb += intfus.dest_i[0].eq(regdecode.dest_o)
        comb += intfus.src_i[0].eq(regdecode.src1_o)
        comb += intfus.src_i[1].eq(regdecode.src2_o)

        fn_issue_o = issueunit.fn_issue_o

        comb += intfus.fn_issue_i.eq(fn_issue_o)
        comb += issueunit.busy_i.eq(cu.busy_o)
        comb += self.busy_o.eq(cu.busy_o.bool())

        # ---------
        # Memory Function Unit
        # ---------
        reset_b = Signal(cul.n_units, reset_less=True)
        # XXX was cul.go_wr_i not done.o
        # sync += reset_b.eq(cul.go_st_i | cul.done_o | cul.go_die_i)
        sync += reset_b.eq(cul.go_st_i | cul.done_o | cul.go_die_i)

        comb += memfus.fn_issue_i.eq(cul.issue_i)  # Comp Unit Issue -> Mem FUs
        comb += memfus.addr_en_i.eq(cul.adr_rel_o)  # Match enable on adr rel
        comb += memfus.addr_rs_i.eq(reset_b)  # reset same as LDSTCompUnit

        # LD/STs have to accumulate prior LD/STs (TODO: multi-issue as well,
        # in a transitive fashion).  This cycle activates based on LDSTCompUnit
        # issue_i.  multi-issue gets a bit more complex but not a lot.
        prior_ldsts = Signal(cul.n_units, reset_less=True)
        sync += prior_ldsts.eq(memfus.g_int_ld_pend_o | memfus.g_int_st_pend_o)
        with m.If(self.ls_oper_i[3]):  # LD bit of operand
            comb += memfus.ld_i.eq(cul.issue_i | prior_ldsts)
        with m.If(self.ls_oper_i[2]):  # ST bit of operand
            comb += memfus.st_i.eq(cul.issue_i | prior_ldsts)

        # TODO: adr_rel_o needs to go into L1 Cache.  for now,
        # just immediately activate go_adr
        sync += cul.go_ad_i.eq(cul.adr_rel_o)

        # connect up address data
        comb += memfus.addrs_i[0].eq(cul.units[0].addr_o)
        comb += memfus.addrs_i[1].eq(cul.units[1].addr_o)

        # connect loadable / storable to go_ld/go_st.
        # XXX should only be done when the memory ld/st has actually happened!
        go_st_i = Signal(cul.n_units, reset_less=True)
        go_ld_i = Signal(cul.n_units, reset_less=True)
        comb += go_ld_i.eq(memfus.loadable_o & memfus.addr_nomatch_o &
                           cul.adr_rel_o & cul.ld_o)
        comb += go_st_i.eq(memfus.storable_o & memfus.addr_nomatch_o &
                           cul.sto_rel_o & cul.st_o)
        comb += memfus.go_ld_i.eq(go_ld_i)
        comb += memfus.go_st_i.eq(go_st_i)
        #comb += cul.go_wr_i.eq(go_ld_i)
        comb += cul.go_st_i.eq(go_st_i)

        #comb += cu.go_rd_i[0:n_intfus].eq(go_rd_o[0:n_intfus])
        #comb += cu.go_wr_i[0:n_intfus].eq(go_wr_o[0:n_intfus])
        #comb += cu.issue_i[0:n_intfus].eq(fn_issue_o[0:n_intfus])

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
        go_rd_o = ipick1.go_rd_o
        go_wr_o = ipick1.go_wr_o
        go_rd_i = intfus.go_rd_i
        go_wr_i = intfus.go_wr_i
        go_die_i = intfus.go_die_i
        # NOTE: connect to the shadowed versions so that they can "die" (reset)
        for i in range(fu_n_src):
            comb += go_rd_i[i][0:n_intfus].eq(go_rd_o[i][0:n_intfus])  # rd
        for i in range(fu_n_dst):
            comb += go_wr_i[i][0:n_intfus].eq(go_wr_o[i][0:n_intfus])  # wr
        comb += go_die_i[0:n_intfus].eq(anydie[0:n_intfus])  # die

        # Connect Picker
        # ---------
        int_rd_o = intfus.readable_o
        rrel_o = cu.rd_rel_o
        rqrl_o = cu.req_rel_o
        for i in range(fu_n_src):
            comb += ipick1.rd_rel_i[i][0:n_intfus].eq(rrel_o[i][0:n_intfus])
            comb += ipick1.readable_i[i][0:n_intfus].eq(int_rd_o[0:n_intfus])
        int_wr_o = intfus.writable_o
        for i in range(fu_n_dst):
            # XXX FIXME: rqrl_o[i] here
            comb += ipick1.req_rel_i[i][0:n_intfus].eq(rqrl_o[0:n_intfus])
            comb += ipick1.writable_i[i][0:n_intfus].eq(int_wr_o[0:n_intfus])

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

        # when written, the shadow can be cancelled (and was good)
        for i in range(n_intfus):
            #comb += shadows.s_good_i[i][0:n_intfus].eq(go_wr_o[0:n_intfus])
            # XXX experiment: use ~cu.busy_o instead.  *should* be good
            # because the comp unit is only free once completed
            comb += shadows.s_good_i[i][0:n_intfus].eq(~cu.busy_o[0:n_intfus])

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
            comb += bspec.good_i.eq(fn_issue_o & 0x1f)  # XXX MAGIC CONSTANT
        with m.If(self.branch_fail_i):
            comb += bspec.fail_i.eq(fn_issue_o & 0x1f)  # XXX MAGIC CONSTANT

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
        comb += int_dest.wen.eq(intfus.dst_rsel_o[0])
        comb += int_src1.ren.eq(intfus.src_rsel_o[0])
        comb += int_src2.ren.eq(intfus.src_rsel_o[1])

        # connect ALUs to regfile
        comb += int_dest.data_i.eq(cu.data_o)
        comb += cu.src1_i.eq(int_src1.data_o)
        comb += cu.src2_i.eq(int_src2.data_o)

        # connect ALU Computation Units
        for i in range(fu_n_src):
            comb += cu.go_rd_i[i][0:n_intfus].eq(go_rd_o[i][0:n_intfus])
        for i in range(fu_n_dst):
            comb += cu.go_wr_i[i][0:n_intfus].eq(go_wr_o[i][0:n_intfus])
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


class IssueToScoreboard(Elaboratable):

    def __init__(self, qlen, n_in, n_out, rwid, opwid, n_regs):
        self.qlen = qlen
        self.n_in = n_in
        self.n_out = n_out
        self.rwid = rwid
        self.opw = opwid
        self.n_regs = n_regs

        mqbits = unsigned(int(log(qlen) / log(2))+2)
        self.p_add_i = Signal(mqbits)  # instructions to add (from data_i)
        self.p_ready_o = Signal()  # instructions were added
        self.data_i = Instruction._nq(n_in, "data_i")

        self.busy_o = Signal(reset_less=True)  # at least one CU is busy
        self.qlen_o = Signal(mqbits, reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        sync = m.d.sync

        iq = InstructionQ(self.rwid, self.opw, self.qlen,
                          self.n_in, self.n_out)
        sc = Scoreboard(self.rwid, self.n_regs)
        m.submodules.iq = iq
        m.submodules.sc = sc

        # get at the regfile for testing
        self.intregs = sc.intregs

        # and the "busy" signal and instruction queue length
        comb += self.busy_o.eq(sc.busy_o)
        comb += self.qlen_o.eq(iq.qlen_o)

        # link up instruction queue
        comb += iq.p_add_i.eq(self.p_add_i)
        comb += self.p_ready_o.eq(iq.p_ready_o)
        for i in range(self.n_in):
            comb += eq(iq.data_i[i], self.data_i[i])

        # take instruction and process it.  note that it's possible to
        # "inspect" the queue contents *without* actually removing the
        # items.  items are only removed when the

        # in "waiting" state
        wait_issue_br = Signal()
        wait_issue_alu = Signal()
        wait_issue_ls = Signal()

        with m.If(wait_issue_br | wait_issue_alu | wait_issue_ls):
            # set instruction pop length to 1 if the unit accepted
            with m.If(wait_issue_ls & (sc.lsissue.fn_issue_o != 0)):
                with m.If(iq.qlen_o != 0):
                    comb += iq.n_sub_i.eq(1)
            with m.If(wait_issue_br & (sc.brissue.fn_issue_o != 0)):
                with m.If(iq.qlen_o != 0):
                    comb += iq.n_sub_i.eq(1)
            with m.If(wait_issue_alu & (sc.aluissue.fn_issue_o != 0)):
                with m.If(iq.qlen_o != 0):
                    comb += iq.n_sub_i.eq(1)

        # see if some instruction(s) are here.  note that this is
        # "inspecting" the in-place queue.  note also that on the
        # cycle following "waiting" for fn_issue_o to be set, the
        # "resetting" done above (insn_i=0) could be re-ASSERTed.
        with m.If(iq.qlen_o != 0):
            # get the operands and operation
            instr = iq.data_o[0]
            imm = instr.imm_data.data
            dest = instr.write_reg.data
            src1 = instr.read_reg1.data
            src2 = instr.read_reg2.data
            op = instr.insn_type
            fu = instr.fn_unit
            opi = instr.imm_data.ok  # immediate set

            # set the src/dest regs
            comb += sc.int_dest_i.eq(dest)
            comb += sc.int_src1_i.eq(src1)
            comb += sc.int_src2_i.eq(src2)
            comb += sc.reg_enable_i.eq(1)  # enable the regfile
            comb += sc.instr.eq(instr)

            # choose a Function-Unit-Group
            with m.If(fu == Function.ALU):  # alu
                comb += sc.aluissue.insn_i.eq(1)  # enable alu issue
                comb += wait_issue_alu.eq(1)
            with m.Elif(fu == Function.LDST):  # ld/st
                comb += sc.lsissue.insn_i.eq(1)  # enable ldst issue
                comb += wait_issue_ls.eq(1)

            with m.Elif((op & (0x3 << 2)) != 0):  # branch
                comb += sc.br_oper_i.eq(Cat(op[0:2], opi))
                comb += sc.br_imm_i.eq(imm)
                comb += sc.brissue.insn_i.eq(1)
                comb += wait_issue_br.eq(1)
            # XXX TODO
            # these indicate that the instruction is to be made
            # shadow-dependent on
            # (either) branch success or branch fail
            # yield sc.branch_fail_i.eq(branch_fail)
            # yield sc.branch_succ_i.eq(branch_success)

        return m

    def __iter__(self):
        yield self.p_ready_o
        for o in self.data_i:
            yield from list(o)
        yield self.p_add_i

    def ports(self):
        return list(self)


def power_instr_q(dut, pdecode2, ins, code):
    instrs = [pdecode2.e]

    sendlen = 1
    for idx, instr in enumerate(instrs):
        yield dut.data_i[idx].eq(instr)
        insn_type = yield instr.insn_type
        fn_unit = yield instr.fn_unit
        print("senddata ", idx, insn_type, fn_unit, instr)
    yield dut.p_add_i.eq(sendlen)
    yield
    o_p_ready = yield dut.p_ready_o
    while not o_p_ready:
        yield
        o_p_ready = yield dut.p_ready_o

    yield dut.p_add_i.eq(0)


def instr_q(dut, op, funit, op_imm, imm, src1, src2, dest,
            branch_success, branch_fail):
    instrs = [{'insn_type': op, 'fn_unit': funit, 'write_reg': dest,
               'imm_data': (imm, op_imm),
               'read_reg1': src1, 'read_reg2': src2}]

    sendlen = 1
    for idx, instr in enumerate(instrs):
        imm, op_imm = instr['imm_data']
        reg1 = instr['read_reg1']
        reg2 = instr['read_reg2']
        dest = instr['write_reg']
        insn_type = instr['insn_type']
        fn_unit = instr['fn_unit']
        yield dut.data_i[idx].insn_type.eq(insn_type)
        yield dut.data_i[idx].fn_unit.eq(fn_unit)
        yield dut.data_i[idx].read_reg1.data.eq(reg1)
        yield dut.data_i[idx].read_reg1.ok.eq(1)  # XXX TODO
        yield dut.data_i[idx].read_reg2.data.eq(reg2)
        yield dut.data_i[idx].read_reg2.ok.eq(1)  # XXX TODO
        yield dut.data_i[idx].write_reg.data.eq(dest)
        yield dut.data_i[idx].write_reg.ok.eq(1)  # XXX TODO
        yield dut.data_i[idx].imm_data.data.eq(imm)
        yield dut.data_i[idx].imm_data.ok.eq(op_imm)
        di = yield dut.data_i[idx]
        print("senddata %d %x" % (idx, di))
    yield dut.p_add_i.eq(sendlen)
    yield
    o_p_ready = yield dut.p_ready_o
    while not o_p_ready:
        yield
        o_p_ready = yield dut.p_ready_o

    yield dut.p_add_i.eq(0)


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


def wait_for_busy_clear(dut):
    while True:
        busy_o = yield dut.busy_o
        if not busy_o:
            break
        print("busy",)
        yield


def disable_issue(dut):
    yield dut.aluissue.insn_i.eq(0)
    yield dut.brissue.insn_i.eq(0)
    yield dut.lsissue.insn_i.eq(0)


def wait_for_issue(dut, dut_issue):
    while True:
        issue_o = yield dut_issue.fn_issue_o
        if issue_o:
            yield from disable_issue(dut)
            yield dut.reg_enable_i.eq(0)
            break
        print("busy",)
        # yield from print_reg(dut, [1,2,3])
        yield
    # yield from print_reg(dut, [1,2,3])


def scoreboard_branch_sim(dut, alusim):

    iseed = 3

    for i in range(1):

        print("rseed", iseed)
        seed(iseed)
        iseed += 1

        yield dut.branch_direction_o.eq(0)

        # set random values in the registers
        for i in range(1, dut.n_regs):
            val = 31+i*3
            val = randint(0, (1 << alusim.rwidth)-1)
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
            op = 4  # only BGT at the moment

            branch_ok = create_random_ops(dut, 1, True, 1)
            branch_fail = create_random_ops(dut, 1, True, 1)

            insts.append((src1, src2, (branch_ok, branch_fail), op, (0, 0)))

        if True:
            insts = []
            insts.append((3, 5, 2, 0, (0, 0)))
            branch_ok = []
            branch_fail = []
            #branch_ok.append  ( (5, 7, 5, 1, (1, 0)) )
            branch_ok.append(None)
            branch_fail.append((1, 1, 2, 0, (0, 1)))
            #branch_fail.append( None )
            insts.append((6, 4, (branch_ok, branch_fail), 4, (0, 0)))

        siminsts = deepcopy(insts)

        # issue instruction(s)
        i = -1
        instrs = insts
        branch_direction = 0
        while instrs:
            yield
            yield
            i += 1
            branch_direction = yield dut.branch_direction_o  # way branch went
            (src1, src2, dest, op, (shadow_on, shadow_off)) = insts.pop(0)
            if branch_direction == 1 and shadow_on:
                print("skip", i, src1, src2, dest, op, shadow_on, shadow_off)
                continue  # branch was "success" and this is a "failed"... skip
            if branch_direction == 2 and shadow_off:
                print("skip", i, src1, src2, dest, op, shadow_on, shadow_off)
                continue  # branch was "fail" and this is a "success"... skip
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
            print("instr %d: (%d, %d, %d, %d, (%d, %d))" %
                  (i, src1, src2, dest, op, shadow_on, shadow_off))
            yield from int_instr(dut, op, src1, src2, dest,
                                 shadow_on, shadow_off)

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
            print("sim %d: (%d, %d, %d, %d, (%d, %d))" %
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


def power_sim(m, dut, pdecode2, instruction, alusim):

    seed(0)

    for i in range(1):

        # set random values in the registers
        for i in range(1, dut.n_regs):
            #val = randint(0, (1<<alusim.rwidth)-1)
            #val = 31+i*3
            val = i  # XXX actually, not random at all
            yield dut.intregs.regs[i].reg.eq(val)
            alusim.setval(i, val)

        # create some instructions
        lst = []
        if False:
            lst += ["addi 2, 0, 0x4321",
                    "addi 3, 0, 0x1234",
                    "add  1, 3, 2",
                    "add  4, 3, 5"
                    ]
        if True:
            lst += ["lbzu 6, 7(2)",

                    ]

        with Program(lst) as program:
            gen = program.generate_instructions()

            # issue instruction(s), wait for issue to be free before proceeding
            for ins, code in zip(gen, program.assembly.splitlines()):
                yield instruction.eq(ins)          # raw binary instr.
                yield  # Delay(1e-6)

                print("binary 0x{:X}".format(ins & 0xffffffff))
                print("assembly", code)

                #alusim.op(op, opi, imm, src1, src2, dest)
                yield from power_instr_q(dut, pdecode2, ins, code)

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


def scoreboard_sim(dut, alusim):

    seed(0)

    for i in range(1):

        # set random values in the registers
        for i in range(1, dut.n_regs):
            #val = randint(0, (1<<alusim.rwidth)-1)
            #val = 31+i*3
            val = i
            yield dut.intregs.regs[i].reg.eq(val)
            alusim.setval(i, val)

        # create some instructions (some random, some regression tests)
        instrs = []
        if False:
            instrs = create_random_ops(dut, 15, True, 4)

        if False:  # LD/ST test (with immediate)
            instrs.append((1, 2, 0, 0x20, 1, 1, (0, 0)))  # LD
            #instrs.append( (1, 2, 0, 0x10, 1, 1, (0, 0)) )

        if False:
            instrs.append((1, 2, 2, 1, 1, 20, (0, 0)))

        if False:
            instrs.append((7, 3, 2, 4, 0, 0, (0, 0)))
            instrs.append((7, 6, 6, 2, 0, 0, (0, 0)))
            instrs.append((1, 7, 2, 2, 0, 0, (0, 0)))

        if True:
            instrs.append((2, 3, 3, MicrOp.OP_ADD, Function.ALU,
                           0, 0, (0, 0)))
            instrs.append((5, 3, 3, MicrOp.OP_ADD, Function.ALU,
                           0, 0, (0, 0)))
        if False:
            instrs.append((3, 5, 5, MicrOp.OP_MUL_L64, Function.ALU,
                           1, 7, (0, 0)))
        if False:
            instrs.append((2, 3, 3, MicrOp.OP_ADD, Function.ALU,
                           0, 0, (0, 0)))

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
            print(i, instr)
            src1, src2, dest, op, fn_unit, opi, imm, (br_ok, br_fail) = instr

            print("instr %d: (%d, %d, %d, %s, %s, %d, %d)" %
                  (i, src1, src2, dest, op, fn_unit, opi, imm))
            alusim.op(op, opi, imm, src1, src2, dest)
            yield from instr_q(dut, op, fn_unit, opi, imm, src1, src2, dest,
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


def test_scoreboard():
    regwidth = 64
    dut = IssueToScoreboard(2, 1, 1, regwidth, 8, 8)
    alusim = RegSim(regwidth, 8)
    memsim = MemSim(16, 8)

    m = Module()
    comb = m.d.comb
    instruction = Signal(32)

    # set up the decoder (and simulator, later)
    pdecode = create_pdecode()
    #simulator = ISA(pdecode, initial_regs)

    m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)
    m.submodules.sim = dut

    comb += pdecode2.dec.raw_opcode_in.eq(instruction)
    comb += pdecode2.dec.bigendian.eq(0)  # little / big?

    vl = rtlil.convert(m, ports=dut.ports())
    with open("test_scoreboard6600.il", "w") as f:
        f.write(vl)

    run_simulation(m, power_sim(m, dut, pdecode2, instruction, alusim),
                   vcd_name='test_powerboard6600.vcd')

    # run_simulation(dut, scoreboard_sim(dut, alusim),
    #               vcd_name='test_scoreboard6600.vcd')

    # run_simulation(dut, scoreboard_branch_sim(dut, alusim),
    #                    vcd_name='test_scoreboard6600.vcd')


if __name__ == '__main__':
    test_scoreboard()
