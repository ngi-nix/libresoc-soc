import unittest
from soc.fu.div.fsm import DivState, DivStateInit, DivStateNext
from nmigen import Elaboratable, Module, Signal, unsigned
from nmigen.cli import rtlil
try:
    from nmigen.sim.pysim import Simulator, Delay, Tick
except ImportError:
    from nmigen.back.pysim import Simulator, Delay, Tick


class CheckEvent(Elaboratable):
    """helper to add indication to vcd when signals are checked
    """

    def __init__(self):
        self.event = Signal()

    def trigger(self):
        yield self.event.eq(~self.event)

    def elaborate(self, platform):
        m = Module()
        # use event somehow so nmigen simulation knows about it
        m.d.comb += Signal().eq(self.event)
        return m


class DivStateCombTest(Elaboratable):
    """Test stringing a bunch of copies of the FSM state-function together
    """

    def __init__(self, quotient_width):
        self.check_event = CheckEvent()
        self.quotient_width = quotient_width
        self.dividend = Signal(unsigned(quotient_width * 2))
        self.divisor = Signal(unsigned(quotient_width))
        self.quotient = Signal(unsigned(quotient_width))
        self.remainder = Signal(unsigned(quotient_width))
        self.expected_quotient = Signal(unsigned(quotient_width))
        self.expected_remainder = Signal(unsigned(quotient_width))
        self.expected_valid = Signal()
        self.states = []
        for i in range(quotient_width + 1):
            state = DivState(quotient_width=quotient_width, name=f"state{i}")
            self.states.append(state)
        self.init = DivStateInit(quotient_width)
        self.nexts = []
        for i in range(quotient_width):
            next = DivStateNext(quotient_width)
            self.nexts.append(next)

    def elaborate(self, platform):
        m = Module()
        m.submodules.check_event = self.check_event
        m.submodules.init = self.init
        m.d.comb += self.init.dividend.eq(self.dividend)
        m.d.comb += self.states[0].eq(self.init.o)
        last_state = self.states[0]
        for i in range(self.quotient_width):
            setattr(m.submodules, f"next{i}", self.nexts[i])
            m.d.comb += self.nexts[i].divisor.eq(self.divisor)
            m.d.comb += self.nexts[i].i.eq(last_state)
            last_state = self.states[i + 1]
            m.d.comb += last_state.eq(self.nexts[i].o)
        m.d.comb += self.quotient.eq(last_state.quotient)
        m.d.comb += self.remainder.eq(last_state.remainder)
        m.d.comb += self.expected_valid.eq(
            (self.dividend < (self.divisor << self.quotient_width))
            & (self.divisor != 0))
        with m.If(self.expected_valid):
            m.d.comb += self.expected_quotient.eq(
                self.dividend // self.divisor)
            m.d.comb += self.expected_remainder.eq(
                self.dividend % self.divisor)
        return m


class DivStateFSMTest(Elaboratable):
    def __init__(self, quotient_width):
        self.check_done_event = CheckEvent()
        self.check_event = CheckEvent()
        self.quotient_width = quotient_width
        self.dividend = Signal(unsigned(quotient_width * 2))
        self.divisor = Signal(unsigned(quotient_width))
        self.quotient = Signal(unsigned(quotient_width))
        self.remainder = Signal(unsigned(quotient_width))
        self.expected_quotient = Signal(unsigned(quotient_width))
        self.expected_remainder = Signal(unsigned(quotient_width))
        self.expected_valid = Signal()
        self.state = DivState(quotient_width=quotient_width,
                              name="state")
        self.next_state = DivState(quotient_width=quotient_width,
                                   name="next_state")
        self.init = DivStateInit(quotient_width)
        self.next = DivStateNext(quotient_width)
        self.state_done = Signal()
        self.next_state_done = Signal()
        self.clear = Signal(reset=1)

    def elaborate(self, platform):
        m = Module()
        m.submodules.check_event = self.check_event
        m.submodules.check_done_event = self.check_done_event
        m.submodules.init = self.init
        m.submodules.next = self.next
        m.d.comb += self.init.dividend.eq(self.dividend)
        m.d.comb += self.next.divisor.eq(self.divisor)
        m.d.comb += self.quotient.eq(self.state.quotient)
        m.d.comb += self.remainder.eq(self.state.remainder)
        m.d.comb += self.next.i.eq(self.state)
        m.d.comb += self.state_done.eq(self.state.done)
        m.d.comb += self.next_state_done.eq(self.next_state.done)

        with m.If(self.state.done | self.clear):
            m.d.comb += self.next_state.eq(self.init.o)
        with m.Else():
            m.d.comb += self.next_state.eq(self.next.o)

        m.d.sync += self.state.eq(self.next_state)

        m.d.comb += self.expected_valid.eq(
            (self.dividend < (self.divisor << self.quotient_width))
            & (self.divisor != 0))
        with m.If(self.expected_valid):
            m.d.comb += self.expected_quotient.eq(
                self.dividend // self.divisor)
            m.d.comb += self.expected_remainder.eq(
                self.dividend % self.divisor)
        return m


def get_cases(quotient_width):
    test_cases = []
    mask = ~(~0 << quotient_width)
    for i in range(-3, 4):
        test_cases.append(i & mask)
    for i in [-1, 0, 1]:
        test_cases.append((i + (mask >> 1)) & mask)
    test_cases.sort()
    return test_cases


class TestDivState(unittest.TestCase):
    def test_div_state_comb(self, quotient_width=8):
        test_cases = get_cases(quotient_width)
        mask = ~(~0 << quotient_width)
        dut = DivStateCombTest(quotient_width)
        vl = rtlil.convert(dut,
                           ports=[dut.dividend,
                                  dut.divisor,
                                  dut.quotient,
                                  dut.remainder])
        with open("div_fsm_comb_pipeline.il", "w") as f:
            f.write(vl)
        dut = DivStateCombTest(quotient_width)

        def check(dividend, divisor):
            with self.subTest(dividend=f"{dividend:#x}",
                              divisor=f"{divisor:#x}"):
                yield from dut.check_event.trigger()
                for i in range(quotient_width + 1):
                    # done must be correct and eventually true
                    # even if a div-by-zero or overflow occurred
                    done = yield dut.states[i].done
                    self.assertEqual(done, i == quotient_width)
                if divisor != 0:
                    quotient = dividend // divisor
                    remainder = dividend % divisor
                    if quotient <= mask:
                        with self.subTest(quotient=f"{quotient:#x}",
                                          remainder=f"{remainder:#x}"):
                            self.assertTrue((yield dut.expected_valid))
                            self.assertEqual((yield dut.expected_quotient),
                                              quotient)
                            self.assertEqual((yield dut.expected_remainder),
                                              remainder)
                            self.assertEqual((yield dut.quotient), quotient)
                            self.assertEqual((yield dut.remainder), remainder)
                    else:
                        self.assertFalse((yield dut.expected_valid))
                else:
                    self.assertFalse((yield dut.expected_valid))

        def process(gen):
            for dividend_high in test_cases:
                for dividend_low in test_cases:
                    dividend = dividend_low + \
                        (dividend_high << quotient_width)
                    for divisor in test_cases:
                        if gen:
                            yield Delay(0.5e-6)
                            yield dut.dividend.eq(dividend)
                            yield dut.divisor.eq(divisor)
                            yield Delay(0.5e-6)
                        else:
                            yield Delay(1e-6)
                            yield from check(dividend, divisor)

        def gen_process():
            yield from process(gen=True)

        def check_process():
            yield from process(gen=False)

        sim = Simulator(dut)
        with sim.write_vcd(vcd_file="div_fsm_comb_pipeline.vcd",
                           gtkw_file="div_fsm_comb_pipeline.gtkw"):

            sim.add_process(gen_process)
            sim.add_process(check_process)
            sim.run()

    def test_div_state_fsm(self, quotient_width=8):
        test_cases = get_cases(quotient_width)
        mask = ~(~0 << quotient_width)
        dut = DivStateFSMTest(quotient_width)
        vl = rtlil.convert(dut,
                           ports=[dut.dividend,
                                  dut.divisor,
                                  dut.quotient,
                                  dut.remainder])
        with open("div_fsm.il", "w") as f:
            f.write(vl)

        def check(dividend, divisor):
            with self.subTest(dividend=f"{dividend:#x}",
                              divisor=f"{divisor:#x}"):
                for i in range(quotient_width + 1):
                    yield Tick()
                    yield Delay(0.1e-6)
                    yield from dut.check_done_event.trigger()
                    with self.subTest():
                        # done must be correct and eventually true
                        # even if a div-by-zero or overflow occurred
                        done = yield dut.state.done
                        self.assertEqual(done, i == quotient_width)
                yield from dut.check_event.trigger()
                now = None
                try:
                    # FIXME(programmerjake): replace with public API
                    # see https://github.com/nmigen/nmigen/issues/443
                    now = sim._engine.now
                except AttributeError:
                    pass
                if divisor != 0:
                    quotient = dividend // divisor
                    remainder = dividend % divisor
                    if quotient <= mask:
                        with self.subTest(quotient=f"{quotient:#x}",
                                          remainder=f"{remainder:#x}",
                                          now=f"{now}"):
                            self.assertTrue((yield dut.expected_valid))
                            self.assertEqual((yield dut.expected_quotient),
                                              quotient)
                            self.assertEqual((yield dut.expected_remainder), 
                                              remainder)
                            self.assertEqual((yield dut.quotient), quotient)
                            self.assertEqual((yield dut.remainder), remainder)
                    else:
                        self.assertFalse((yield dut.expected_valid))
                else:
                    self.assertFalse((yield dut.expected_valid))

        def process(gen):
            if gen:
                yield dut.clear.eq(1)
                yield Tick()
            else:
                yield from dut.check_event.trigger()
                yield from dut.check_done_event.trigger()
            for dividend_high in test_cases:
                for dividend_low in test_cases:
                    dividend = dividend_low + \
                        (dividend_high << quotient_width)
                    for divisor in test_cases:
                        if gen:
                            yield Delay(0.2e-6)
                            yield dut.clear.eq(0)
                            yield dut.dividend.eq(dividend)
                            yield dut.divisor.eq(divisor)
                            for _ in range(quotient_width + 1):
                                yield Tick()
                        else:
                            yield from check(dividend, divisor)

        def gen_process():
            yield from process(gen=True)

        def check_process():
            yield from process(gen=False)

        sim = Simulator(dut)
        with sim.write_vcd(vcd_file="div_fsm.vcd",
                           gtkw_file="div_fsm.gtkw"):

            sim.add_clock(1e-6)
            sim.add_process(gen_process)
            sim.add_process(check_process)
            sim.run()


if __name__ == "__main__":
    unittest.main()
