from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Cat, Array, Const, Repl, Elaboratable
from nmutil.iocontrol import RecordObject
from nmutil.nmoperator import eq, shape, cat


class Instruction(RecordObject):
    def __init__(self, name, wid, opwid):
        RecordObject.__init__(self, name=name)
        self.oper_i = Signal(opwid, reset_less=True)
        self.dest_i = Signal(wid, reset_less=True)
        self.src1_i = Signal(wid, reset_less=True)
        self.src2_i = Signal(wid, reset_less=True)

    @staticmethod
    def nq(n_insns, name, wid, opwid):
        q = []
        for i in range(n_insns):
            q.append(Instruction("%s%d" % (name, i), wid, opwid))
        return Array(q)


class InstructionQ(Elaboratable):
    """ contains a queue of (part-decoded) instructions.

        it is expected that the user of this queue will simply
        inspect the queue contents directly, indicating at the start
        of each clock cycle how many need to be removed.
    """
    def __init__(self, wid, opwid, iqlen, n_in, n_out):
        """ constructor

            Inputs

            * :wid:         register file width
            * :opwid:       operand width
            * :iqlen:       instruction queue length
            * :n_in:        max number of instructions allowed "in"
        """
        self.iqlen = iqlen
        self.reg_width = wid
        self.opwid = opwid
        self.n_in = n_in
        self.n_out = n_out

        self.p_add_i = Signal(max=n_in) # instructions to add (from data_i)
        self.p_ready_o = Signal() # instructions were added
        self.data_i = Instruction.nq(n_in, "data_i", wid, opwid)
        
        self.data_o = Instruction.nq(n_out, "data_o", wid, opwid)
        self.n_sub_i = Signal(max=n_out) # number of instructions to remove
        self.n_sub_o = Signal(max=n_out) # number of instructions removed

        self.qsz = shape(self.data_o[0])[0]
        q = []
        for i in range(iqlen):
            q.append(Signal(self.qsz, name="q%d" % i))
        self.q = Array(q)
        self.qlen_o = Signal(max=iqlen)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        sync = m.d.sync

        iqlen = self.iqlen
        mqlen = Const(iqlen, iqlen+1)

        start_copy = Signal(max=iqlen*2)
        end_copy = Signal(max=iqlen*2)

        # work out how many can be subtracted from the queue
        with m.If(self.n_sub_i >= self.qlen_o):
            comb += self.n_sub_o.eq(self.qlen_o)
        with m.Elif(self.n_sub_i):
            comb += self.n_sub_o.eq(self.n_sub_i)

        # work out the start and end of where data can be written
        comb += start_copy.eq(self.qlen_o - self.n_sub_o)
        comb += end_copy.eq(start_copy + self.p_add_i)
        comb += self.p_ready_o.eq((end_copy < self.qlen_o) & self.p_add_i)

        # put q (flattened) into output
        for i in range(self.n_out):
            comb += cat(self.data_o[i]).eq(self.q[i])

        # this is going to be _so_ expensive in terms of gates... *sigh*...
        with m.If(self.p_ready_o):
            for i in range(iqlen-1):
                cfrom = Signal(max=iqlen*2)
                cto = Signal(max=iqlen*2)
                comb += cfrom.eq(Const(i, iqlen+1) + start_copy)
                comb += cto.eq(Const(i, iqlen+1) + end_copy)
                with m.If((cfrom < mqlen) & (cto < mqlen)):
                    sync += self.q[cto].eq(self.q[cfrom])

        for i in range(self.n_in):
            with m.If(self.p_add_i < i):
                idx = Signal(max=iqlen)
                comb += idx.eq(start_copy + i)
                sync += self.q[idx].eq(cat(self.data_i[i]))

        return m

    def __iter__(self):
        yield from self.q

        yield self.p_ready_o
        for o in self.data_i:
            yield from list(o)
        yield self.p_add_i
        
        for o in self.data_o:
            yield from list(o)
        yield self.n_sub_i
        yield self.n_sub_o

    def ports(self):
        return list(self)


def instruction_q_sim(dut):
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

def test_instruction_q():
    dut = InstructionQ(16, 4, 4, n_in=2, n_out=2)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_instruction_q.il", "w") as f:
        f.write(vl)

    run_simulation(dut, instruction_q_sim(dut),
                   vcd_name='test_instruction_q.vcd')

if __name__ == '__main__':
    test_instruction_q()
