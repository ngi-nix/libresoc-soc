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
from soc.fu.cr.cr_input_record import CompCROpSubset
from soc.experiment.alu_hier import ALU, DummyALU
from soc.experiment.compalu_multi import MultiCompUnit
from openpower.decoder.power_enums import MicrOp
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


def scoreboard_sim_dummy(op):
    yield from op.issue([5, 2, 0], MicrOp.OP_NOP, [5],
                        src_delays=[0, 2, 1], dest_delays=[0])
    yield from op.issue([9, 2, 0], MicrOp.OP_NOP, [9],
                        src_delays=[2, 1, 0], dest_delays=[2])
    # test all combinations of masked input ports
    yield from op.issue([5, 2, 0], MicrOp.OP_NOP, [0],
                        rdmaskn=[1, 0, 0],
                        src_delays=[0, 2, 1], dest_delays=[0])
    yield from op.issue([9, 2, 0], MicrOp.OP_NOP, [9],
                        rdmaskn=[0, 1, 0],
                        src_delays=[2, 1, 0], dest_delays=[2])
    yield from op.issue([5, 2, 0], MicrOp.OP_NOP, [5],
                        rdmaskn=[0, 0, 1],
                        src_delays=[2, 1, 0], dest_delays=[2])
    yield from op.issue([9, 2, 0], MicrOp.OP_NOP, [9],
                        rdmaskn=[0, 1, 1],
                        src_delays=[2, 1, 0], dest_delays=[2])
    yield from op.issue([9, 2, 0], MicrOp.OP_NOP, [0],
                        rdmaskn=[1, 1, 0],
                        src_delays=[2, 1, 0], dest_delays=[2])
    yield from op.issue([9, 2, 0], MicrOp.OP_NOP, [0],
                        rdmaskn=[1, 1, 1],
                        src_delays=[2, 1, 0], dest_delays=[2])


class OpSim:
    """ALU Operation issuer

    Issues operations to the DUT"""
    def __init__(self, dut, sim):
        self.op_count = 0
        self.zero_a_count = 0
        self.imm_ok_count = 0
        self.rdmaskn_count = [0] * len(dut.src_i)
        self.wrmask_count = [0] * len(dut.dest)
        self.dut = dut
        # create one operand producer for each input port
        self.producers = list()
        for i in range(len(dut.src_i)):
            self.producers.append(OperandProducer(sim, dut, i))
        # create one result consumer for each output port
        self.consumers = list()
        for i in range(len(dut.dest)):
            self.consumers.append(ResultConsumer(sim, dut, i))

    def issue(self, src_i, op, expected, src_delays, dest_delays,
              inv_a=0, imm=0, imm_ok=0, zero_a=0, rc=0,
              rdmaskn=None, wrmask=None):
        """Executes the issue operation"""
        dut = self.dut
        producers = self.producers
        consumers = self.consumers
        if rdmaskn is None:
            rdmaskn = [0] * len(src_i)
        if wrmask is None:
            wrmask = [0] * len(expected)
        yield dut.issue_i.eq(0)
        yield
        # forward data and delays to the producers and consumers
        # first, send special cases (with zero_a and/or imm_ok)
        if not zero_a:
            yield from producers[0].send(src_i[0], src_delays[0])
        if not imm_ok:
            yield from producers[1].send(src_i[1], src_delays[1])
        # then, send the rest (if any)
        for i in range(2, len(producers)):
            yield from producers[i].send(src_i[i], src_delays[i])
        for i in range(len(consumers)):
            yield from consumers[i].receive(expected[i], dest_delays[i])
        # submit operation, and assert issue_i for one cycle
        yield dut.oper_i.insn_type.eq(op)
        if hasattr(dut.oper_i, "invert_in"):
            yield dut.oper_i.invert_in.eq(inv_a)
        if hasattr(dut.oper_i, "imm_data"):
            yield dut.oper_i.imm_data.data.eq(imm)
            yield dut.oper_i.imm_data.ok.eq(imm_ok)
        if hasattr(dut.oper_i, "zero_a"):
            yield dut.oper_i.zero_a.eq(zero_a)
        if hasattr(dut.oper_i, "rc"):
            yield dut.oper_i.rc.rc.eq(rc)
        if hasattr(dut, "rdmaskn"):
            rdmaskn_bits = 0
            for i in range(len(rdmaskn)):
                rdmaskn_bits |= rdmaskn[i] << i
            yield dut.rdmaskn.eq(rdmaskn_bits)
        yield dut.issue_i.eq(1)
        yield
        yield dut.issue_i.eq(0)
        # deactivate decoder inputs along with issue_i, so we can be sure they
        # were latched at the correct cycle
        # note: rdmaskn is not latched, and must be held as long as
        # busy_o is active
        # See: https://bugs.libre-soc.org/show_bug.cgi?id=336#c44
        yield self.dut.oper_i.insn_type.eq(0)
        if hasattr(dut.oper_i, "invert_in"):
            yield self.dut.oper_i.invert_in.eq(0)
        if hasattr(dut.oper_i, "imm_data"):
            yield self.dut.oper_i.imm_data.data.eq(0)
            yield self.dut.oper_i.imm_data.ok.eq(0)
        if hasattr(dut.oper_i, "zero_a"):
            yield self.dut.oper_i.zero_a.eq(0)
        if hasattr(dut.oper_i, "rc"):
            yield dut.oper_i.rc.rc.eq(0)
        # wait for busy to be negated
        yield Settle()
        while (yield dut.busy_o):
            yield
            yield Settle()
        # now, deactivate rdmaskn
        if hasattr(dut, "rdmaskn"):
            yield dut.rdmaskn.eq(0)
        # update the operation count
        self.op_count = (self.op_count + 1) & 255
        # On zero_a, imm_ok and rdmaskn executions, the producer counters will
        # fall behind. But, by summing the following counts, the invariant is
        # preserved.
        if zero_a and not rdmaskn[0]:
            self.zero_a_count += 1
        if imm_ok and not rdmaskn[1]:
            self.imm_ok_count += 1
        for i in range(len(rdmaskn)):
            if rdmaskn[i]:
                self.rdmaskn_count[i] += 1
        for i in range(len(wrmask)):
            if wrmask[i]:
                self.wrmask_count[i] += 1
        # check that producers and consumers have the same count
        # this assures that no data was left unused or was lost
        # first, check special cases (zero_a and imm_ok)
        port_a_cnt = \
            (yield producers[0].count) \
            + self.zero_a_count \
            + self.rdmaskn_count[0]
        port_b_cnt = \
            (yield producers[1].count) \
            + self.imm_ok_count \
            + self.rdmaskn_count[1]
        assert port_a_cnt == self.op_count
        assert port_b_cnt == self.op_count
        # then, check the rest (if any)
        for i in range(2, len(producers)):
            port_cnt = (yield producers[i].count) + self.rdmaskn_count[i]
            assert port_cnt == self.op_count
        # check write counter
        for i in range(len(consumers)):
            port_cnt = (yield consumers[i].count) + self.wrmask_count[i]
            assert port_cnt == self.op_count


def scoreboard_sim(op):
    # the following tests cases have rc=0, so no CR output is expected
    # zero (no) input operands test
    # 0 + 8 = 8
    yield from op.issue([5, 2], MicrOp.OP_ADD, [8, 0],
                        zero_a=1, imm=8, imm_ok=1,
                        wrmask=[0, 1],
                        src_delays=[0, 2], dest_delays=[0, 0])
    # 5 + 8 = 13
    yield from op.issue([5, 2], MicrOp.OP_ADD, [13, 0],
                        inv_a=0, imm=8, imm_ok=1,
                        wrmask=[0, 1],
                        src_delays=[2, 0], dest_delays=[2, 0])
    # 5 + 2 = 7
    yield from op.issue([5, 2], MicrOp.OP_ADD, [7, 0],
                        wrmask=[0, 1],
                        src_delays=[1, 1], dest_delays=[1, 0])
    # (-6) + 2 = (-4)
    yield from op.issue([5, 2], MicrOp.OP_ADD, [65532, 0],
                        inv_a=1,
                        wrmask=[0, 1],
                        src_delays=[1, 2], dest_delays=[0, 0])
    # 0 + 2 = 2
    yield from op.issue([5, 2], MicrOp.OP_ADD, [2, 0],
                        zero_a=1,
                        wrmask=[0, 1],
                        src_delays=[2, 0], dest_delays=[1, 0])

    # test combinatorial zero-delay operation
    # In the test ALU, any operation other than ADD, MUL, EXTS or SHR
    # is zero-delay, and do a subtraction.
    # 5 - 2 = 3
    yield from op.issue([5, 2], MicrOp.OP_CMP, [3, 0],
                        wrmask=[0, 1],
                        src_delays=[0, 1], dest_delays=[2, 0])
    # test all combinations of masked input ports
    # NOP does not make any request nor response
    yield from op.issue([5, 2], MicrOp.OP_NOP, [0, 0],
                        rdmaskn=[1, 1], wrmask=[1, 1],
                        src_delays=[1, 2], dest_delays=[1, 0])
    # sign_extend(0x80) = 0xFF80
    yield from op.issue([0x80, 2], MicrOp.OP_EXTS, [0xFF80, 0],
                        rdmaskn=[0, 1], wrmask=[0, 1],
                        src_delays=[2, 1], dest_delays=[0, 0])
    # sign_extend(0x80) = 0xFF80
    yield from op.issue([2, 0x80], MicrOp.OP_EXTSWSLI, [0xFF80, 0],
                        rdmaskn=[1, 0], wrmask=[0, 1],
                        src_delays=[1, 2], dest_delays=[1, 0])
    # test with rc=1, so expect results on the CR output port
    # 5 + 2 = 7
    # 7 > 0 => CR = 0b100
    yield from op.issue([5, 2], MicrOp.OP_ADD, [7, 0b100],
                        rc=1,
                        src_delays=[1, 1], dest_delays=[1, 0])
    # sign_extend(0x80) = 0xFF80
    # -128 < 0 => CR = 0b010
    yield from op.issue([0x80, 2], MicrOp.OP_EXTS, [0xFF80, 0b010],
                        rc=1, rdmaskn=[0, 1],
                        src_delays=[2, 1], dest_delays=[0, 2])
    # 5 - 5 = 0
    # 0 == 0 => CR = 0b001
    yield from op.issue([5, 2], MicrOp.OP_CMP, [0, 0b001],
                        imm=5, imm_ok=1, rc=1,
                        src_delays=[0, 1], dest_delays=[2, 1])


def test_compunit_fsm():
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
        ('alu', {'submodule': 'alu'}, [
            ('prev port', 'in', [
                'op__sdir', 'p_data_i[7:0]', 'p_shift_i[7:0]',
                ({'submodule': 'p'},
                    ['p_valid_i', 'p_ready_o'])]),
            ('next port', 'out', [
                'n_data_o[7:0]',
                ({'submodule': 'n'},
                    ['n_valid_o', 'n_ready_i'])])]),
        ('debug', {'module': 'top'},
            ['src1_count[7:0]', 'src2_count[7:0]', 'dest1_count[7:0]'])]

    write_gtkw(
        "test_compunit_fsm1.gtkw",
        "test_compunit_fsm1.vcd",
        traces, style,
        module='top.cu'
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
    dut = MultiCompUnit(16, alu, CompALUOpSubset, n_dst=2)
    m.submodules.cu = dut

    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_compunit1.il", "w") as f:
        f.write(vl)

    sim = Simulator(m)
    sim.add_clock(1e-6)

    # create an operation issuer
    op = OpSim(dut, sim)
    sim.add_sync_process(wrap(scoreboard_sim(op)))
    sim_writer = sim.write_vcd('test_compunit1.vcd')
    with sim_writer:
        sim.run()


def test_compunit_regspec2_fsm():

    inspec = [('INT', 'data', '0:15'),
              ('INT', 'shift', '0:15')]
    outspec = [('INT', 'data', '0:15')]

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

    style = {
        'in': {'color': 'orange'},
        'out': {'color': 'yellow'},
    }
    traces = [
        'clk',
        ('operation port', {'color': 'red'}, [
            'cu_issue_i', 'cu_busy_o',
            {'comment': 'operation'},
            ('oper_i_None__insn_type'
             + ('' if is_engine_pysim() else '[6:0]'),
             {'display': 'insn_type'})]),
        ('operand 1 port', 'in', [
            ('cu_rdmaskn_i[2:0]', {'bit': 2}),
            ('cu_rd__rel_o[2:0]', {'bit': 2}),
            ('cu_rd__go_i[2:0]', {'bit': 2}),
            'src1_i[15:0]']),
        ('operand 2 port', 'in', [
            ('cu_rdmaskn_i[2:0]', {'bit': 1}),
            ('cu_rd__rel_o[2:0]', {'bit': 1}),
            ('cu_rd__go_i[2:0]', {'bit': 1}),
            'src2_i[15:0]']),
        ('operand 3 port', 'in', [
            ('cu_rdmaskn_i[2:0]', {'bit': 0}),
            ('cu_rd__rel_o[2:0]', {'bit': 0}),
            ('cu_rd__go_i[2:0]', {'bit': 0}),
            'src1_i[15:0]']),
        ('result port', 'out', [
            'cu_wrmask_o', 'cu_wr__rel_o', 'cu_wr__go_i', 'dest1_o[15:0]']),
        ('alu', {'submodule': 'alu'}, [
            ('prev port', 'in', [
                'oper_i_None__insn_type', 'i1[15:0]',
                'valid_i', 'ready_o']),
            ('next port', 'out', [
                'alu_o[15:0]', 'valid_o', 'ready_i'])])]

    write_gtkw("test_compunit_regspec3.gtkw",
               "test_compunit_regspec3.vcd",
               traces, style,
               clk_period=1e-6,
               module='top.cu')

    inspec = [('INT', 'a', '0:15'),
              ('INT', 'b', '0:15'),
              ('INT', 'c', '0:15')]
    outspec = [('INT', 'o', '0:15')]

    regspec = (inspec, outspec)

    m = Module()
    alu = DummyALU(16)
    dut = MultiCompUnit(regspec, alu, CompCROpSubset)
    m.submodules.cu = dut

    sim = Simulator(m)
    sim.add_clock(1e-6)

    # create an operation issuer
    op = OpSim(dut, sim)
    sim.add_sync_process(wrap(scoreboard_sim_dummy(op)))
    sim_writer = sim.write_vcd('test_compunit_regspec3.vcd')
    with sim_writer:
        sim.run()


def test_compunit_regspec1():

    style = {
        'in': {'color': 'orange'},
        'out': {'color': 'yellow'},
    }
    traces = [
        'clk',
        ('operation port', {'color': 'red'}, [
            'cu_issue_i', 'cu_busy_o',
            {'comment': 'operation'},
            ('oper_i_None__insn_type'
             + ('' if is_engine_pysim() else '[6:0]'),
             {'display': 'insn_type'}),
            ('oper_i_None__invert_in', {'display': 'invert_in'}),
            ('oper_i_None__imm_data__data[63:0]', {'display': 'data[63:0]'}),
            ('oper_i_None__imm_data__ok', {'display': 'imm_ok'}),
            ('oper_i_None__zero_a', {'display': 'zero_a'}),
            ('oper_i_None__rc__rc', {'display': 'rc'})]),
        ('operand 1 port', 'in', [
            ('cu_rdmaskn_i[1:0]', {'bit': 1}),
            ('cu_rd__rel_o[1:0]', {'bit': 1}),
            ('cu_rd__go_i[1:0]', {'bit': 1}),
            'src1_i[15:0]']),
        ('operand 2 port', 'in', [
            ('cu_rdmaskn_i[1:0]', {'bit': 0}),
            ('cu_rd__rel_o[1:0]', {'bit': 0}),
            ('cu_rd__go_i[1:0]', {'bit': 0}),
            'src2_i[15:0]']),
        ('result port', 'out', [
            ('cu_wrmask_o[1:0]', {'bit': 1}),
            ('cu_wr__rel_o[1:0]', {'bit': 1}),
            ('cu_wr__go_i[1:0]', {'bit': 1}),
            'dest1_o[15:0]']),
        ('cr port', 'out', [
            ('cu_wrmask_o[1:0]', {'bit': 0}),
            ('cu_wr__rel_o[1:0]', {'bit': 0}),
            ('cu_wr__go_i[1:0]', {'bit': 0}),
            'dest2_o[15:0]']),
        ('alu', {'submodule': 'alu'}, [
            ('prev port', 'in', [
                'op__insn_type', 'op__invert_in', 'a[15:0]', 'b[15:0]',
                'valid_i', 'ready_o']),
            ('next port', 'out', [
                'alu_o[15:0]', 'valid_o', 'ready_i',
                'alu_o_ok', 'alu_cr_ok'])]),
        ('debug', {'module': 'top'},
            ['src1_count[7:0]', 'src2_count[7:0]', 'dest1_count[7:0]'])]

    write_gtkw("test_compunit_regspec1.gtkw",
               "test_compunit_regspec1.vcd",
               traces, style,
               clk_period=1e-6,
               module='top.cu')

    inspec = [('INT', 'a', '0:15'),
              ('INT', 'b', '0:15')]
    outspec = [('INT', 'o', '0:15'),
               ('INT', 'cr', '0:15')]

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

    # create an operation issuer
    op = OpSim(dut, sim)
    sim.add_sync_process(wrap(scoreboard_sim(op)))
    sim_writer = sim.write_vcd('test_compunit_regspec1.vcd',
                               traces=[op.producers[0].count,
                                       op.producers[1].count,
                                       op.consumers[0].count])
    with sim_writer:
        sim.run()


if __name__ == '__main__':
    test_compunit()
    test_compunit_fsm()
    test_compunit_regspec1()
    test_compunit_regspec2_fsm()
    test_compunit_regspec3()
