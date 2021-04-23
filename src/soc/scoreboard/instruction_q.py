from math import log

from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Cat, Array, Const, Repl, Elaboratable
from nmutil.iocontrol import RecordObject
from nmutil.nmoperator import eq, shape, cat

from openpower.decoder.power_decoder2 import Decode2ToExecute1Type


class Instruction(Decode2ToExecute1Type):

    @staticmethod
    def _nq(n_insns, name):
        q = []
        for i in range(n_insns):
            q.append(Instruction("%s%d" % (name, i)))
        return Array(q)


class InstructionQ(Elaboratable):
    """ contains a queue of (part-decoded) instructions.

        output is copied combinatorially from the front of the queue,
        for easy access on the clock cycle.  only "n_in" instructions
        are made available this way

        input and shifting occurs on sync.
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
        mqbits = (int(log(iqlen) / log(2))+2, False)

        self.p_add_i = Signal(mqbits)  # instructions to add (from data_i)
        self.p_ready_o = Signal()  # instructions were added
        self.data_i = Instruction._nq(n_in, "data_i")

        self.data_o = Instruction._nq(n_out, "data_o")
        self.n_sub_i = Signal(mqbits)  # number of instructions to remove
        self.n_sub_o = Signal(mqbits)  # number of instructions removed

        self.qsz = shape(self.data_o[0])[0]
        q = []
        for i in range(iqlen):
            q.append(Signal(self.qsz, name="q%d" % i))
        self.q = Array(q)
        self.qlen_o = Signal(mqbits)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        sync = m.d.sync

        iqlen = self.iqlen
        mqbits = int(log(iqlen) / log(2))

        left = Signal((mqbits+2, False))
        spare = Signal((mqbits+2, False))
        qmaxed = Signal()

        start_q = Signal(mqbits)
        end_q = Signal(mqbits)
        mqlen = Const(iqlen, (len(left), False))
        print("mqlen", mqlen)

        # work out how many can be subtracted from the queue
        with m.If(self.n_sub_i):
            qinmax = Signal()
            comb += qinmax.eq(self.n_sub_i > self.qlen_o)
            with m.If(qinmax):
                comb += self.n_sub_o.eq(self.qlen_o)
            with m.Else():
                comb += self.n_sub_o.eq(self.n_sub_i)

        # work out how many new items are going to be in the queue
        comb += left.eq(self.qlen_o)  # - self.n_sub_o)
        comb += spare.eq(mqlen - self.p_add_i)
        comb += qmaxed.eq(left <= spare)
        comb += self.p_ready_o.eq(qmaxed & (self.p_add_i != 0))

        # put q (flattened) into output
        for i in range(self.n_out):
            opos = Signal(mqbits)
            comb += opos.eq(end_q + i)
            comb += cat(self.data_o[i]).eq(self.q[opos])

        with m.If(self.n_sub_o):
            # ok now the end's moved
            sync += end_q.eq(end_q + self.n_sub_o)

        with m.If(self.p_ready_o):
            # copy in the input... insanely gate-costly... *sigh*...
            for i in range(self.n_in):
                with m.If(self.p_add_i > Const(i, len(self.p_add_i))):
                    ipos = Signal(mqbits)
                    comb += ipos.eq(start_q + i)  # should roll round
                    sync += self.q[ipos].eq(cat(self.data_i[i]))
            sync += start_q.eq(start_q + self.p_add_i)

        with m.If(self.p_ready_o):
            # update the queue length
            add2 = Signal(mqbits+1)
            comb += add2.eq(self.qlen_o + self.p_add_i)
            sync += self.qlen_o.eq(add2 - self.n_sub_o)
        with m.Else():
            sync += self.qlen_o.eq(self.qlen_o - self.n_sub_o)

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
