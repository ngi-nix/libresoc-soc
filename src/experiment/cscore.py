from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Const, Signal, Array, Cat, Elaboratable

from regfile.regfile import RegFileArray, treereduce
from scoreboard.fn_unit import IntFnUnit, FPFnUnit, LDFnUnit, STFnUnit
from scoreboard.fu_fu_matrix import FUFUDepMatrix
from scoreboard.fu_reg_matrix import FURegDepMatrix
from scoreboard.global_pending import GlobalPending
from scoreboard.group_picker import GroupPicker
from scoreboard.issue_unit import IntFPIssueUnit

from compalu import ComputationUnitNoDelay

from alu_hier import ALU
from nmutil.latch import SRLatch


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

        # Int ALUs
        add = ALU(self.rwid)
        sub = ALU(self.rwid)
        m.submodules.comp1 = comp1 = ComputationUnitNoDelay(self.rwid, 1, add)
        m.submodules.comp2 = comp2 = ComputationUnitNoDelay(self.rwid, 1, sub)
        int_alus = [comp1, comp2]

        m.d.comb += comp1.oper_i.eq(Const(0)) # temporary/experiment: op=add
        m.d.comb += comp2.oper_i.eq(Const(1)) # temporary/experiment: op=sub

        # Int FUs
        il = []
        int_rd_pend_v = []
        int_wr_pend_v = []
        for i, a in enumerate(int_alus):
            # set up Integer Function Unit, add to module (and python list)
            fu = IntFnUnit(self.rwid, shadow_wid=0)
            setattr(m.submodules, "intfu%d" % i, fu)
            il.append(fu)
            # collate the read/write pending vectors (to go into global pending)
            int_rd_pend_v.append(fu.int_rd_pend_o)
            int_wr_pend_v.append(fu.int_wr_pend_o)
        int_fus = Array(il)

        # Count of number of FUs
        n_int_fus = len(il)
        n_fp_fus = 0 # for now

        n_fus = n_int_fus + n_fp_fus # plus FP FUs

        # XXX replaced by array of FUs? *FnUnit
        # # Integer FU-FU Dep Matrix
        # m.submodules.intfudeps = FUFUDepMatrix(n_int_fus, n_int_fus)
        # Integer FU-Reg Dep Matrix
        # intregdeps = FURegDepMatrix(self.n_regs, n_int_fus)
        # m.submodules.intregdeps = intregdeps

        # Integer Priority Picker 1: Adder + Subtractor
        intpick1 = GroupPicker(2) # picks between add and sub
        m.submodules.intpick1 = intpick1

        # Global Pending Vectors (INT and FP)
        # NOTE: number of vectors is NOT same as number of FUs.
        g_int_rd_pend_v = GlobalPending(self.rwid, int_rd_pend_v)
        g_int_wr_pend_v = GlobalPending(self.rwid, int_wr_pend_v)
        m.submodules.g_int_rd_pend_v = g_int_rd_pend_v
        m.submodules.g_int_wr_pend_v = g_int_wr_pend_v

        # INT/FP Issue Unit
        issueunit = IntFPIssueUnit(self.rwid, n_int_fus, n_fp_fus)
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
                     issueunit.i.dest_i.eq(self.int_dest_i),
                     issueunit.i.src1_i.eq(self.int_src1_i),
                     issueunit.i.src2_i.eq(self.int_src2_i)
                    ]
        self.int_insn_i = issueunit.i.insn_i # enabled by instruction decode

        # connect global rd/wr pending vectors
        m.d.comb += issueunit.i.g_wr_pend_i.eq(g_int_wr_pend_v.g_pend_o)
        # TODO: issueunit.f (FP)

        # and int function issue / busy arrays, and dest/src1/src2
        fn_issue_l = []
        fn_busy_l = []
        for i, fu in enumerate(il):
            fn_issue_l.append(fu.issue_i)
            fn_busy_l.append(fu.busy_o)
            m.d.comb += fu.issue_i.eq(issueunit.i.fn_issue_o[i])
            m.d.comb += fu.dest_i.eq(issueunit.i.dest_i)
            m.d.comb += fu.src1_i.eq(issueunit.i.src1_i)
            m.d.comb += fu.src2_i.eq(issueunit.i.src2_i)
            m.d.comb += issueunit.i.busy_i[i].eq(fu.busy_o)

        #---------
        # connect Function Units
        #---------

        # Group Picker... done manually for now.  TODO: cat array of pick sigs
        m.d.comb += il[0].go_rd_i.eq(intpick1.go_rd_o[0]) # add rd
        m.d.comb += il[0].go_wr_i.eq(intpick1.go_wr_o[0]) # add wr

        m.d.comb += il[1].go_rd_i.eq(intpick1.go_rd_o[1]) # subtract rd
        m.d.comb += il[1].go_wr_i.eq(intpick1.go_wr_o[1]) # subtract wr

        # Connect INT Fn Unit global wr/rd pending
        for fu in il:
            m.d.comb += fu.g_int_wr_pend_i.eq(g_int_wr_pend_v.g_pend_o)
            m.d.comb += fu.g_int_rd_pend_i.eq(g_int_rd_pend_v.g_pend_o)

        # Connect Picker
        #---------
        m.d.comb += intpick1.req_rel_i[0].eq(int_alus[0].req_rel_o)
        m.d.comb += intpick1.req_rel_i[1].eq(int_alus[1].req_rel_o)
        m.d.comb += intpick1.readable_i[0].eq(il[0].int_readable_o) # add rdable
        m.d.comb += intpick1.writable_i[0].eq(il[0].int_writable_o) # add rdable
        m.d.comb += intpick1.readable_i[1].eq(il[1].int_readable_o) # sub rdable
        m.d.comb += intpick1.writable_i[1].eq(il[1].int_writable_o) # sub rdable

        #---------
        # Connect Register File(s)
        #---------
        m.d.comb += int_dest.wen.eq(g_int_wr_pend_v.g_pend_o)
        m.d.comb += int_src1.ren.eq(g_int_rd_pend_v.g_pend_o)
        m.d.comb += int_src2.ren.eq(g_int_rd_pend_v.g_pend_o)

        # merge (OR) all integer FU / ALU outputs to a single value
        # bit of a hack: treereduce needs a list with an item named "dest_o"
        dest_o = treereduce(int_alus)
        m.d.comb += int_dest.data_i.eq(dest_o)

        # connect ALUs
        for i, alu in enumerate(int_alus):
            m.d.comb += alu.go_rd_i.eq(il[i].go_rd_i) # chained from intpick
            m.d.comb += alu.go_wr_i.eq(il[i].go_wr_i) # chained from intpick
            m.d.comb += alu.issue_i.eq(fn_issue_l[i])
            #m.d.comb += fn_busy_l[i].eq(alu.busy_o)  # XXX ignore, use fnissue
            m.d.comb += alu.src1_i.eq(int_src1.data_o)
            m.d.comb += alu.src2_i.eq(int_src2.data_o)
            m.d.comb += il[i].req_rel_i.eq(alu.req_rel_o) # pipe out ready

        return m


    def __iter__(self):
        yield from self.intregs
        yield from self.fpregs
        #yield from self.int_src1
        #yield from self.int_dest
        #yield from self.int_src1
        #yield from self.int_src2
        #yield from self.fp_dest
        #yield from self.fp_src1
        #yield from self.fp_src2

    def ports(self):
        return list(self)


def scoreboard_sim(dut):
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

def test_scoreboard():
    dut = Scoreboard(32, 8)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_scoreboard.il", "w") as f:
        f.write(vl)

    run_simulation(dut, scoreboard_sim(dut), vcd_name='test_scoreboard.vcd')

if __name__ == '__main__':
    test_scoreboard()
