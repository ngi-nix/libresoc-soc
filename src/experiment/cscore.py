from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Array, Elaboratable

from regfile.regfile import RegFileArray
from scoreboard.fn_unit import IntFnUnit, FPFnUnit, LDFnUnit, STFnUnit
from scoreboard.fu_fu_matrix import FUFUDepMatrix

from alu_hier import Adder, Subtractor

class Scoreboard(Elaboratable):
    def __init__(self, reg_width, reg_depth):
        self.reg_width = reg_width
        self.reg_depth = reg_depth

        # Register Files
        self.intregs = RegFileArray(reg_width, reg_depth)
        self.int_dest = self.intregs.write_port()
        self.int_src1 = self.intregs.read_port()
        self.int_src2 = self.intregs.read_port()

        self.fpregs = RegFileArray(reg_width, reg_depth)
        self.fp_dest = self.fpregs.write_port()
        self.fp_src1 = self.fpregs.read_port()
        self.fp_src2 = self.fpregs.read_port()

    def elaborate(self, platform):
        m = Module()
        m.submodules.intregs = self.intregs
        m.submodules.fpregs = self.fpregs

        # Int ALUs
        m.submodules.adder = adder = Adder(self.reg_width)
        m.submodules.subtractor = subtractor = Subtractor(self.reg_width)
        int_alus = [adder, subtractor]

        # Int FUs
        il = []
        for i, a in enumerate(int_alus):
            fu = IntFnUnit(self.reg_width, shadow_wid=0)
            setattr(m.submodules, "intfu%d" % i, fu)
            il.append(fu)
        int_fus = Array(il)

        n_fus = len(il)

        # FU Dep Matrix
        m.submodules.fudeps = fudeps = FUFUDepMatrix(n_fus, n_fus)


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
