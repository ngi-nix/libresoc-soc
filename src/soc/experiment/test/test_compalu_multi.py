"""Computation Unit (aka "ALU Manager").

Manages a Pipeline or FSM, ensuring that the start and end time are 100%
monitored.  At no time may the ALU proceed without this module notifying
the Dependency Matrices.  At no time is a result production "abandoned".
This module blocks (indicates busy) starting from when it first receives
an opcode until it receives notification that
its result(s) have been successfully stored in the regfile(s)

Documented at http://libre-soc.org/3d_gpu/architecture/compunit
"""

from soc.experiment.alu_fsm import Shifter, CompFSMOpSubset
from soc.fu.alu.alu_input_record import CompALUOpSubset
from soc.experiment.alu_hier import ALU, DummyALU
from soc.experiment.compalu_multi import MultiCompUnit
from soc.decoder.power_enums import MicrOp
from nmutil.gtkw import write_gtkw
from nmigen import Module, Signal
from nmigen.cli import rtlil

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git
from nmutil.sim_tmp_alternative import (Simulator, Settle, is_engine_pysim,
                                        Passive)


def wrap(process):
    def wrapper():
        yield from process
    return wrapper


class OperandProducer:
    """
    Produces an operand when requested by the Computation Unit
    (`dut` parameter), using the `rel_o` / `go_i` handshake.

    Attaches itself to the `dut` operand indexed by `op_index`.

    Has a programmable delay between the assertion of `rel_o` and the
    `go_i` pulse.

    Data is presented only during the cycle in which `go_i` is active.

    It adds itself as a passive process to the simulation (`sim` parameter).
    Since it is passive, it will not hang the simulation, and does not need a
    flag to terminate itself.
    """
    def __init__(self, sim, dut, op_index):
        self.count = Signal(8, name=f"src{op_index + 1}_count")
        """ transaction counter"""
        # data and handshake signals from the DUT
        self.port = dut.src_i[op_index]
        self.go_i = dut.rd.go_i[op_index]
        self.rel_o = dut.rd.rel_o[op_index]
        # transaction parameters, passed via signals
        self.delay = Signal(8)
        self.data = Signal.like(self.port)
        # add ourselves to the simulation process list
        sim.add_sync_process(self._process)

    def _process(self):
        yield Passive()
        while True:
            # Settle() is needed to give a quick response to
            # the zero delay case
            yield Settle()
            # wait for rel_o to become active
            while not (yield self.rel_o):
                yield
                yield Settle()
            # read the transaction parameters
            delay = (yield self.delay)
            data = (yield self.data)
            # wait for `delay` cycles
            for _ in range(delay):
                yield
            # activate go_i and present data, for one cycle
            yield self.go_i.eq(1)
            yield self.port.eq(data)
            yield self.count.eq(self.count + 1)
            yield
            yield self.go_i.eq(0)
            yield self.port.eq(0)

    def send(self, data, delay):
        """
        Schedules the module to send some `data`, counting `delay` cycles after
        `rel_i` becomes active.

        To be called from the main test-bench process,
        it returns in the same cycle.

        Communication with the worker process is done by means of
        combinatorial simulation-only signals.

        """
        yield self.data.eq(data)
        yield self.delay.eq(delay)


class ResultConsumer:
    """
    Consumes a result when requested by the Computation Unit
    (`dut` parameter), using the `rel_o` / `go_i` handshake.

    Attaches itself to the `dut` result indexed by `op_index`.

    Has a programmable delay between the assertion of `rel_o` and the
    `go_i` pulse.

    Data is retrieved only during the cycle in which `go_i` is active.

    It adds itself as a passive process to the simulation (`sim` parameter).
    Since it is passive, it will not hang the simulation, and does not need a
    flag to terminate itself.
    """
    def __init__(self, sim, dut, op_index):
        self.count = Signal(8, name=f"dest{op_index + 1}_count")
        """ transaction counter"""
        # data and handshake signals from the DUT
        self.port = dut.dest[op_index]
        self.go_i = dut.wr.go_i[op_index]
        self.rel_o = dut.wr.rel_o[op_index]
        # transaction parameters, passed via signals
        self.delay = Signal(8)
        self.expected = Signal.like(self.port)
        # add ourselves to the simulation process list
        sim.add_sync_process(self._process)

    def _process(self):
        yield Passive()
        while True:
            # Settle() is needed to give a quick response to
            # the zero delay case
            yield Settle()
            # wait for rel_o to become active
            while not (yield self.rel_o):
                yield
                yield Settle()
            # read the transaction parameters
            delay = (yield self.delay)
            expected = (yield self.expected)
            # wait for `delay` cycles
            for _ in range(delay):
                yield
            # activate go_i for one cycle
            yield self.go_i.eq(1)
            yield self.count.eq(self.count + 1)
            yield
            # check received data against the expected value
            result = (yield self.port)
            assert result == expected,\
                f"expected {expected}, received {result}"
            yield self.go_i.eq(0)
            yield self.port.eq(0)

    def receive(self, expected, delay):
        """
        Schedules the module to receive some result,
        counting `delay` cycles after `rel_i` becomes active.
        As 'go_i' goes active, check the result with `expected`.

        To be called from the main test-bench process,
        it returns in the same cycle.

        Communication with the worker process is done by means of
        combinatorial simulation-only signals.
        """
        yield self.expected.eq(expected)
        yield self.delay.eq(delay)


def op_sim(dut, a, b, op, inv_a=0, imm=0, imm_ok=0, zero_a=0):
    yield dut.issue_i.eq(0)
    yield
    yield dut.src_i[0].eq(a)
    yield dut.src_i[1].eq(b)
    yield dut.oper_i.insn_type.eq(op)
    yield dut.oper_i.invert_in.eq(inv_a)
    yield dut.oper_i.imm_data.data.eq(imm)
    yield dut.oper_i.imm_data.ok.eq(imm_ok)
    yield dut.oper_i.zero_a.eq(zero_a)
    yield dut.issue_i.eq(1)
    yield
    yield dut.issue_i.eq(0)
    yield
    if not imm_ok or not zero_a:
        yield dut.rd.go_i.eq(0b11)
        while True:
            yield
            rd_rel_o = yield dut.rd.rel_o
            print("rd_rel", rd_rel_o)
            if rd_rel_o:
                break
        yield dut.rd.go_i.eq(0)
    else:
        print("no go rd")

    if len(dut.src_i) == 3:
        yield dut.rd.go_i.eq(0b100)
        while True:
            yield
            rd_rel_o = yield dut.rd.rel_o
            print("rd_rel", rd_rel_o)
            if rd_rel_o:
                break
        yield dut.rd.go_i.eq(0)
    else:
        print("no 3rd rd")

    req_rel_o = yield dut.wr.rel_o
    result = yield dut.data_o
    print("req_rel", req_rel_o, result)
    while True:
        req_rel_o = yield dut.wr.rel_o
        result = yield dut.data_o
        print("req_rel", req_rel_o, result)
        if req_rel_o:
            break
        yield
    yield dut.wr.go_i[0].eq(1)
    yield Settle()
    result = yield dut.data_o
    yield
    print("result", result)
    yield dut.wr.go_i[0].eq(0)
    yield
    return result


def scoreboard_sim_fsm(dut, producers, consumers):

    # stores the operation count
    op_count = 0

    def op_sim_fsm(a, b, direction, expected, delays):
        print("op_sim_fsm", a, b, direction, expected)
        yield dut.issue_i.eq(0)
        yield
        # forward data and delays to the producers and consumers
        yield from producers[0].send(a, delays[0])
        yield from producers[1].send(b, delays[1])
        yield from consumers[0].receive(expected, delays[2])
        # submit operation, and assert issue_i for one cycle
        yield dut.oper_i.sdir.eq(direction)
        yield dut.issue_i.eq(1)
        yield
        yield dut.issue_i.eq(0)
        # wait for busy to be negated
        yield Settle()
        while (yield dut.busy_o):
            yield
            yield Settle()
        # update the operation count
        nonlocal op_count
        op_count = (op_count + 1) & 255
        # check that producers and consumers have the same count
        # this assures that no data was left unused or was lost
        assert (yield producers[0].count) == op_count
        assert (yield producers[1].count) == op_count
        assert (yield consumers[0].count) == op_count

    # 13 >> 2 = 3
    # operand 1 arrives immediately
    # operand 2 arrives after operand 1
    # write data is accepted immediately
    yield from op_sim_fsm(13, 2, 1, 3, [0, 2, 0])
    # 3 << 4 = 48
    # operand 2 arrives immediately
    # operand 1 arrives after operand 2
    # write data is accepted after some delay
    yield from op_sim_fsm(3, 4, 0, 48, [2, 0, 2])
    # 21 << 0 = 21
    # operands 1 and 2 arrive at the same time
    # write data is accepted after some delay
    yield from op_sim_fsm(21, 0, 0, 21, [1, 1, 1])


def scoreboard_sim_dummy(dut):
    result = yield from op_sim(dut, 5, 2, MicrOp.OP_NOP, inv_a=0,
                               imm=8, imm_ok=1)
    assert result == 5, result

    result = yield from op_sim(dut, 9, 2, MicrOp.OP_NOP, inv_a=0,
                               imm=8, imm_ok=1)
    assert result == 9, result


def scoreboard_sim(dut):
    # zero (no) input operands test
    result = yield from op_sim(dut, 5, 2, MicrOp.OP_ADD, zero_a=1,
                               imm=8, imm_ok=1)
    assert result == 8

    result = yield from op_sim(dut, 5, 2, MicrOp.OP_ADD, inv_a=0,
                               imm=8, imm_ok=1)
    assert result == 13

    result = yield from op_sim(dut, 5, 2, MicrOp.OP_ADD)
    assert result == 7

    result = yield from op_sim(dut, 5, 2, MicrOp.OP_ADD, inv_a=1)
    assert result == 65532

    result = yield from op_sim(dut, 5, 2, MicrOp.OP_ADD, zero_a=1)
    assert result == 2

    # test combinatorial zero-delay operation
    # In the test ALU, any operation other than ADD, MUL or SHR
    # is zero-delay, and do a subtraction.
    result = yield from op_sim(dut, 5, 2, MicrOp.OP_NOP)
    assert result == 3


def test_compunit_fsm():
    top = "top.cu" if is_engine_pysim() else "cu"
    style = {
        'in': {'color': 'orange'},
        'out': {'color': 'yellow'},
    }
    traces = [
        'clk',
        ('operation port', {'color': 'red'}, [
            'cu_issue_i', 'cu_busy_o',
            {'comment': 'operation'},
            'oper_i_None__sdir']),
        ('operand 1 port', 'in', [
            ('cu_rd__rel_o[1:0]', {'bit': 1}),
            ('cu_rd__go_i[1:0]', {'bit': 1}),
            'src1_i[7:0]']),
        ('operand 2 port', 'in', [
            ('cu_rd__rel_o[1:0]', {'bit': 0}),
            ('cu_rd__go_i[1:0]', {'bit': 0}),
            'src2_i[7:0]']),
        ('result port', 'out', [
            'cu_wr__rel_o', 'cu_wr__go_i', 'dest1_o[7:0]']),
        ('alu', {'module': top+'.alu'}, [
            ('prev port', 'in', [
                'op__sdir', 'p_data_i[7:0]', 'p_shift_i[7:0]',
                'p_valid_i', 'p_ready_o']),
            ('next port', 'out', [
                'n_data_o[7:0]', 'n_valid_o', 'n_ready_i']),
        ]),
        ('debug', {'module': 'top'},
         ['src1_count[7:0]', 'src2_count[7:0]', 'dest1_count[7:0]'])

    ]
    write_gtkw(
        "test_compunit_fsm1.gtkw",
        "test_compunit_fsm1.vcd",
        traces, style,
        module=top
    )
    m = Module()
    alu = Shifter(8)
    dut = MultiCompUnit(8, alu, CompFSMOpSubset)
    m.submodules.cu = dut

    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_compunit_fsm1.il", "w") as f:
        f.write(vl)

    sim = Simulator(m)
    sim.add_clock(1e-6)

    # create one operand producer for each input port
    prod_a = OperandProducer(sim, dut, 0)
    prod_b = OperandProducer(sim, dut, 1)
    # create an result consumer for the output port
    cons = ResultConsumer(sim, dut, 0)
    sim.add_sync_process(wrap(scoreboard_sim_fsm(dut,
                                                 [prod_a, prod_b],
                                                 [cons])))
    sim_writer = sim.write_vcd('test_compunit_fsm1.vcd',
                               traces=[prod_a.count,
                                       prod_b.count,
                                       cons.count])
    with sim_writer:
        sim.run()


def test_compunit():

    m = Module()
    alu = ALU(16)
    dut = MultiCompUnit(16, alu, CompALUOpSubset)
    m.submodules.cu = dut

    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_compunit1.il", "w") as f:
        f.write(vl)

    sim = Simulator(m)
    sim.add_clock(1e-6)

    sim.add_sync_process(wrap(scoreboard_sim(dut)))
    sim_writer = sim.write_vcd('test_compunit1.vcd')
    with sim_writer:
        sim.run()


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
        yield from self.operation(5, 2, MicrOp.OP_ADD)

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
        yield self.dut.oper_i.invert_in.eq(self.inv_a)
        yield self.dut.oper_i.imm_data.data.eq(self.imm)
        yield self.dut.oper_i.imm_data.ok.eq(self.imm_ok)
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
        yield self.dut.oper_i.invert_in.eq(0)
        yield self.dut.oper_i.imm_data.data.eq(0)
        yield self.dut.oper_i.imm_data.ok.eq(0)
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
            rel = yield self.dut.rd.rel_o[rd_idx]
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
        rel = yield self.dut.rd.rel_o[rd_idx]
        assert not rel

        # stall for additional cycles. Check that rel doesn't fall on its own
        for n in range(self.RD_GO_DELAY[rd_idx]):
            yield
            rel = yield self.dut.rd.rel_o[rd_idx]
            assert rel

        # Before asserting "go", make sure "rel" has risen.
        # The use of Settle allows "go" to be set combinatorially,
        # rising on the same cycle as "rel".
        yield Settle()
        rel = yield self.dut.rd.rel_o[rd_idx]
        assert rel

        # assert go for one cycle, passing along the operand value
        yield self.dut.rd.go_i[rd_idx].eq(1)
        yield self.dut.src_i[rd_idx].eq(self.operands[rd_idx])
        # check that the operand was sent to the alu
        # TODO: Properly check the alu protocol
        yield Settle()
        alu_input = yield self.dut.get_in(rd_idx)
        assert alu_input == self.operands[rd_idx]
        yield

        # rel must keep high, since go was inactive in the last cycle
        rel = yield self.dut.rd.rel_o[rd_idx]
        assert rel

        # finish the go one-clock pulse
        yield self.dut.rd.go_i[rd_idx].eq(0)
        yield self.dut.src_i[rd_idx].eq(0)
        yield

        # rel must have gone low in response to go being high
        # on the previous cycle
        rel = yield self.dut.rd.rel_o[rd_idx]
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
        m = Module()
        m.submodules.cu = self.dut
        sim = Simulator(m)
        sim.add_clock(1e-6)

        sim.add_sync_process(wrap(self.driver()))
        sim.add_sync_process(wrap(self.rd(0)))
        sim.add_sync_process(wrap(self.rd(1)))
        sim.add_sync_process(wrap(self.wr(0)))
        sim_writer = sim.write_vcd(vcd_name)
        with sim_writer:
            sim.run()


def test_compunit_regspec2_fsm():

    inspec = [('INT', 'data', '0:15'),
              ('INT', 'shift', '0:15'),
              ]
    outspec = [('INT', 'data', '0:15'),
               ]

    regspec = (inspec, outspec)

    m = Module()
    alu = Shifter(8)
    dut = MultiCompUnit(regspec, alu, CompFSMOpSubset)
    m.submodules.cu = dut

    sim = Simulator(m)
    sim.add_clock(1e-6)

    # create one operand producer for each input port
    prod_a = OperandProducer(sim, dut, 0)
    prod_b = OperandProducer(sim, dut, 1)
    # create an result consumer for the output port
    cons = ResultConsumer(sim, dut, 0)
    sim.add_sync_process(wrap(scoreboard_sim_fsm(dut,
                                                 [prod_a, prod_b],
                                                 [cons])))
    sim_writer = sim.write_vcd('test_compunit_regspec2_fsm.vcd',
                               traces=[prod_a.count,
                                       prod_b.count,
                                       cons.count])
    with sim_writer:
        sim.run()


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

    sim = Simulator(m)
    sim.add_clock(1e-6)

    sim.add_sync_process(wrap(scoreboard_sim_dummy(dut)))
    sim_writer = sim.write_vcd('test_compunit_regspec3.vcd')
    with sim_writer:
        sim.run()


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

    sim = Simulator(m)
    sim.add_clock(1e-6)

    sim.add_sync_process(wrap(scoreboard_sim(dut)))
    sim_writer = sim.write_vcd('test_compunit_regspec1.vcd')
    with sim_writer:
        sim.run()

    test = CompUnitParallelTest(dut)
    test.run_simulation("test_compunit_parallel.vcd")


if __name__ == '__main__':
    test_compunit()
    test_compunit_fsm()
    test_compunit_regspec1()
    test_compunit_regspec2_fsm()
    test_compunit_regspec3()
