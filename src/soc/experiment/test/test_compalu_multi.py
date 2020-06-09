"""Computation Unit (aka "ALU Manager").

Manages a Pipeline or FSM, ensuring that the start and end time are 100%
monitored.  At no time may the ALU proceed without this module notifying
the Dependency Matrices.  At no time is a result production "abandoned".
This module blocks (indicates busy) starting from when it first receives
an opcode until it receives notification that
its result(s) have been successfully stored in the regfile(s)

Documented at http://libre-soc.org/3d_gpu/architecture/compunit
"""

from nmigen.compat.sim import run_simulation, Settle
from nmigen.cli import rtlil
from nmigen import Module

from soc.decoder.power_enums import InternalOp

from soc.experiment.compalu_multi import MultiCompUnit
from soc.experiment.alu_hier import ALU, DummyALU
from soc.fu.alu.alu_input_record import CompALUOpSubset


def op_sim(dut, a, b, op, inv_a=0, imm=0, imm_ok=0, zero_a=0):
    yield dut.issue_i.eq(0)
    yield
    yield dut.src_i[0].eq(a)
    yield dut.src_i[1].eq(b)
    yield dut.oper_i.insn_type.eq(op)
    yield dut.oper_i.invert_a.eq(inv_a)
    yield dut.oper_i.imm_data.imm.eq(imm)
    yield dut.oper_i.imm_data.imm_ok.eq(imm_ok)
    yield dut.oper_i.zero_a.eq(zero_a)
    yield dut.issue_i.eq(1)
    yield
    yield dut.issue_i.eq(0)
    yield
    if not imm_ok or not zero_a:
        yield dut.rd.go.eq(0b11)
        while True:
            yield
            rd_rel_o = yield dut.rd.rel
            print ("rd_rel", rd_rel_o)
            if rd_rel_o:
                break
        yield dut.rd.go.eq(0)
    if len(dut.src_i) == 3:
        yield dut.rd.go.eq(0b100)
        while True:
            yield
            rd_rel_o = yield dut.rd.rel
            print ("rd_rel", rd_rel_o)
            if rd_rel_o:
                break
        yield dut.rd.go.eq(0)

    req_rel_o = yield dut.wr.rel
    result = yield dut.data_o
    print ("req_rel", req_rel_o, result)
    while True:
        req_rel_o = yield dut.wr.rel
        result = yield dut.data_o
        print ("req_rel", req_rel_o, result)
        if req_rel_o:
            break
        yield
    yield dut.wr.go[0].eq(1)
    yield Settle()
    result = yield dut.data_o
    yield
    print ("result", result)
    yield dut.wr.go[0].eq(0)
    yield
    return result


def scoreboard_sim_dummy(dut):
    result = yield from op_sim(dut, 5, 2, InternalOp.OP_NOP, inv_a=0,
                                    imm=8, imm_ok=1)
    assert result == 5, result

    result = yield from op_sim(dut, 9, 2, InternalOp.OP_NOP, inv_a=0,
                                    imm=8, imm_ok=1)
    assert result == 9, result


def scoreboard_sim(dut):
    result = yield from op_sim(dut, 5, 2, InternalOp.OP_ADD, inv_a=0,
                                    imm=8, imm_ok=1)
    assert result == 13

    result = yield from op_sim(dut, 5, 2, InternalOp.OP_ADD)
    assert result == 7

    result = yield from op_sim(dut, 5, 2, InternalOp.OP_ADD, inv_a=1)
    assert result == 65532

    result = yield from op_sim(dut, 5, 2, InternalOp.OP_ADD, zero_a=1,
                                    imm=8, imm_ok=1)
    assert result == 8

    result = yield from op_sim(dut, 5, 2, InternalOp.OP_ADD, zero_a=1)
    assert result == 2

    # test combinatorial zero-delay operation
    # In the test ALU, any operation other than ADD, MUL or SHR
    # is zero-delay, and do a subtraction.
    result = yield from op_sim(dut, 5, 2, InternalOp.OP_NOP)
    assert result == 3


def test_compunit():

    m = Module()
    alu = ALU(16)
    dut = MultiCompUnit(16, alu, CompALUOpSubset)
    m.submodules.cu = dut

    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_compunit1.il", "w") as f:
        f.write(vl)

    run_simulation(m, scoreboard_sim(dut), vcd_name='test_compunit1.vcd')


class CompUnitParallelTest:
    def __init__(self, dut):
        self.dut = dut

        # Operation cycle should not take longer than this:
        self.MAX_BUSY_WAIT = 50

        # Minimum duration in which issue_i will be kept inactive,
        # during which busy_o must remain low.
        self.MIN_BUSY_LOW = 5

        # Number of cycles to stall until the assertion of go.
        # One value, for each port. Can be zero, for no delay.
        self.RD_GO_DELAY = [0, 3]

        # store common data for the input operation of the processes
        # input operation:
        self.op = 0
        self.inv_a = self.zero_a = 0
        self.imm = self.imm_ok = 0
        self.imm_control = (0, 0)
        self.rdmaskn = (0, 0)
        # input data:
        self.operands = (0, 0)

        # Indicates completion of the sub-processes
        self.rd_complete = [False, False]

    def driver(self):
        print("Begin parallel test.")
        yield from self.operation(5, 2, InternalOp.OP_NOP, inv_a=0,
                                  imm=8, imm_ok=0, rdmaskn=(1, 0))

    def operation(self, a, b, op, inv_a=0, imm=0, imm_ok=0, zero_a=0,
                  rdmaskn=(0, 0)):
        # store data for the operation
        self.operands = (a, b)
        self.op = op
        self.inv_a = inv_a
        self.imm = imm
        self.imm_ok = imm_ok
        self.zero_a = zero_a
        self.imm_control = (zero_a, imm_ok)
        self.rdmaskn = rdmaskn

        # Initialize completion flags
        self.rd_complete = [False, False]

        # trigger operation cycle
        yield from self.issue()

        # check that the sub-processes completed, before the busy_o cycle ended
        for completion in self.rd_complete:
            assert completion

    def issue(self):
        # issue_i starts inactive
        yield self.dut.issue_i.eq(0)

        for n in range(self.MIN_BUSY_LOW):
            yield
            # busy_o must remain inactive. It cannot rise on its own.
            busy_o = yield self.dut.busy_o
            assert not busy_o

        # activate issue_i to begin the operation cycle
        yield self.dut.issue_i.eq(1)

        # at the same time, present the operation
        yield self.dut.oper_i.insn_type.eq(self.op)
        yield self.dut.oper_i.invert_a.eq(self.inv_a)
        yield self.dut.oper_i.imm_data.imm.eq(self.imm)
        yield self.dut.oper_i.imm_data.imm_ok.eq(self.imm_ok)
        yield self.dut.oper_i.zero_a.eq(self.zero_a)
        rdmaskn = self.rdmaskn[0] | (self.rdmaskn[1] << 1)
        yield self.dut.rdmaskn.eq(rdmaskn)

        # give one cycle for the CompUnit to latch the data
        yield

        # busy_o must keep being low in this cycle, because issue_i was
        # low on the previous cycle.
        # It cannot rise on its own.
        # Also, busy_o and issue_i must never be active at the same time, ever.
        busy_o = yield self.dut.busy_o
        assert not busy_o

        # Lower issue_i
        yield self.dut.issue_i.eq(0)

        # deactivate inputs along with issue_i, so we can be sure the data
        # was latched at the correct cycle
        # note: rdmaskn must be held, while busy_o is active
        # TODO: deactivate rdmaskn when the busy_o cycle ends
        yield self.dut.oper_i.insn_type.eq(0)
        yield self.dut.oper_i.invert_a.eq(0)
        yield self.dut.oper_i.imm_data.imm.eq(0)
        yield self.dut.oper_i.imm_data.imm_ok.eq(0)
        yield self.dut.oper_i.zero_a.eq(0)
        yield

        # wait for busy_o to lower
        # timeout after self.MAX_BUSY_WAIT cycles
        for n in range(self.MAX_BUSY_WAIT):
            # sample busy_o in the current cycle
            busy_o = yield self.dut.busy_o
            if not busy_o:
                # operation cycle ends when busy_o becomes inactive
                break
            yield

        # if busy_o is still active, a timeout has occurred
        # TODO: Uncomment this, once the test is complete:
        # assert not busy_o

        if busy_o:
            print("If you are reading this, "
                  "it's because the above test failed, as expected,\n"
                  "with a timeout. It must pass, once the test is complete.")
            return

        print("If you are reading this, "
              "it's because the above test unexpectedly passed.")

    def rd(self, rd_idx):
        # wait for issue_i to rise
        while True:
            issue_i = yield self.dut.issue_i
            if issue_i:
                break
            # issue_i has not risen yet, so rd must keep low
            rel = yield self.dut.rd.rel[rd_idx]
            assert not rel
            yield

        # we do not want rd to rise on an immediate operand
        # if it is immediate, exit the process
        # likewise, if the read mask is active
        # TODO: don't exit the process, monitor rd instead to ensure it
        #       doesn't rise on its own
        if self.rdmaskn[rd_idx] or self.imm_control[rd_idx]:
            self.rd_complete[rd_idx] = True
            return

        # issue_i has risen. rel must rise on the next cycle
        rel = yield self.dut.rd.rel[rd_idx]
        assert not rel

        # stall for additional cycles. Check that rel doesn't fall on its own
        for n in range(self.RD_GO_DELAY[rd_idx]):
            yield
            rel = yield self.dut.rd.rel[rd_idx]
            assert rel

        # Before asserting "go", make sure "rel" has risen.
        # The use of Settle allows "go" to be set combinatorially,
        # rising on the same cycle as "rel".
        yield Settle()
        rel = yield self.dut.rd.rel[rd_idx]
        assert rel

        # assert go for one cycle, passing along the operand value
        yield self.dut.rd.go[rd_idx].eq(1)
        yield self.dut.src_i[rd_idx].eq(self.operands[rd_idx])
        # check that the operand was sent to the alu
        # TODO: Properly check the alu protocol
        yield Settle()
        alu_input = yield self.dut.get_in(rd_idx)
        assert alu_input == self.operands[rd_idx]
        yield

        # rel must keep high, since go was inactive in the last cycle
        rel = yield self.dut.rd.rel[rd_idx]
        assert rel

        # finish the go one-clock pulse
        yield self.dut.rd.go[rd_idx].eq(0)
        yield self.dut.src_i[rd_idx].eq(0)
        yield

        # rel must have gone low in response to go being high
        # on the previous cycle
        rel = yield self.dut.rd.rel[rd_idx]
        assert not rel

        self.rd_complete[rd_idx] = True

        # TODO: check that rel doesn't rise again until the end of the
        #       busy_o cycle

    def wr(self, wr_idx):
        # monitor self.dut.wr.req[rd_idx] and sets dut.wr.go[idx] for one cycle
        yield
        # TODO: also when dut.wr.go is set, check the output against the
        # self.expected_o and assert.  use dut.get_out(wr_idx) to do so.

    def run_simulation(self, vcd_name):
        run_simulation(self.dut, [self.driver(),
                                  self.rd(0),  # one read port (a)
                                  self.rd(1),  # one read port (b)
                                  self.wr(0),  # one write port (o)
                                  ],
                       vcd_name=vcd_name)


def test_compunit_regspec3():

    inspec = [('INT', 'a', '0:15'),
              ('INT', 'b', '0:15'),
              ('INT', 'c', '0:15')]
    outspec = [('INT', 'o', '0:15'),
              ]

    regspec = (inspec, outspec)

    m = Module()
    alu = DummyALU(16)
    dut = MultiCompUnit(regspec, alu, CompALUOpSubset)
    m.submodules.cu = dut

    run_simulation(m, scoreboard_sim_dummy(dut),
                   vcd_name='test_compunit_regspec3.vcd')


def test_compunit_regspec1():

    inspec = [('INT', 'a', '0:15'),
              ('INT', 'b', '0:15')]
    outspec = [('INT', 'o', '0:15'),
              ]

    regspec = (inspec, outspec)

    m = Module()
    alu = ALU(16)
    dut = MultiCompUnit(regspec, alu, CompALUOpSubset)
    m.submodules.cu = dut

    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_compunit_regspec1.il", "w") as f:
        f.write(vl)

    run_simulation(m, scoreboard_sim(dut),
                   vcd_name='test_compunit_regspec1.vcd')

    test = CompUnitParallelTest(dut)
    test.run_simulation("test_compunit_parallel.vcd")


if __name__ == '__main__':
    test_compunit()
    test_compunit_regspec1()
    test_compunit_regspec3()
