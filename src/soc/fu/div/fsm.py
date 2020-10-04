import enum
from nmigen import Elaboratable, Module, Signal, Shape, unsigned, Cat, Mux
from soc.fu.div.pipe_data import CoreInputData, CoreOutputData, DivPipeSpec
from nmutil.iocontrol import PrevControl, NextControl
from nmutil.singlepipe import ControlBase
from ieee754.div_rem_sqrt_rsqrt.core import DivPipeCoreOperation


class FSMDivCoreConfig:
    n_stages = 1
    bit_width = 64
    fract_width = 64


class FSMDivCoreInputData:
    def __init__(self, core_config, reset_less=True):
        self.core_config = core_config
        self.dividend = Signal(128, reset_less=reset_less)
        self.divisor_radicand = Signal(64, reset_less=reset_less)
        self.operation = DivPipeCoreOperation.create_signal(
            reset_less=reset_less)

    def __iter__(self):
        """ Get member signals. """
        yield self.dividend
        yield self.divisor_radicand
        yield self.operation

    def eq(self, rhs):
        """ Assign member signals. """
        return [self.dividend.eq(rhs.dividend),
                self.divisor_radicand.eq(rhs.divisor_radicand),
                self.operation.eq(rhs.operation),
                ]


class FSMDivCoreOutputData:
    def __init__(self, core_config, reset_less=True):
        self.core_config = core_config
        self.quotient_root = Signal(64, reset_less=reset_less)
        self.remainder = Signal(3 * 64, reset_less=reset_less)

    def __iter__(self):
        """ Get member signals. """
        yield self.quotient_root
        yield self.remainder
        return

    def eq(self, rhs):
        """ Assign member signals. """
        return [self.quotient_root.eq(rhs.quotient_root),
                self.remainder.eq(rhs.remainder)]


class DivStateNext(Elaboratable):
    def __init__(self, quotient_width):
        self.quotient_width = quotient_width
        self.i = DivState(quotient_width=quotient_width, name="i")
        self.divisor = Signal(quotient_width)
        self.o = DivState(quotient_width=quotient_width, name="o")

    def elaborate(self, platform):
        m = Module()
        difference = Signal(self.i.quotient_width * 2)
        m.d.comb += difference.eq(self.i.dividend_quotient
                                  - (self.divisor
                                     << (self.quotient_width - 1)))
        next_quotient_bit = Signal()
        m.d.comb += next_quotient_bit.eq(
            ~difference[self.quotient_width * 2 - 1])
        value = Signal(self.i.quotient_width * 2)
        with m.If(next_quotient_bit):
            m.d.comb += value.eq(difference)
        with m.Else():
            m.d.comb += value.eq(self.i.dividend_quotient)

        with m.If(self.i.done):
            m.d.comb += self.o.eq(self.i)
        with m.Else():
            m.d.comb += [
                self.o.q_bits_known.eq(self.i.q_bits_known + 1),
                self.o.dividend_quotient.eq(Cat(next_quotient_bit, value))]
        return m


class DivStateInit(Elaboratable):
    def __init__(self, quotient_width):
        self.quotient_width = quotient_width
        self.dividend = Signal(quotient_width * 2)
        self.o = DivState(quotient_width=quotient_width, name="o")

    def elaborate(self, platform):
        m = Module()
        m.d.comb += self.o.q_bits_known.eq(0)
        m.d.comb += self.o.dividend_quotient.eq(self.dividend)
        return m


class DivState:
    def __init__(self, quotient_width, name):
        self.quotient_width = quotient_width
        self.q_bits_known = Signal(range(1 + quotient_width),
                                   name=name + "_q_bits_known")
        self.dividend_quotient = Signal(unsigned(2 * quotient_width),
                                        name=name + "_dividend_quotient")

    @property
    def done(self):
        return self.will_be_done_after(steps=0)

    def will_be_done_after(self, steps):
        """ Returns 1 if this state will be done after
            another `steps` passes through DivStateNext."""
        assert isinstance(steps, int), "steps must be an integer"
        assert steps >= 0
        return self.q_bits_known >= max(0, self.quotient_width - steps)

    @property
    def quotient(self):
        """ get the quotient -- requires self.done is True """
        return self.dividend_quotient[0:self.quotient_width]

    @property
    def remainder(self):
        """ get the remainder -- requires self.done is True """
        return self.dividend_quotient[self.quotient_width:self.quotient_width*2]

    def eq(self, rhs):
        return [self.q_bits_known.eq(rhs.q_bits_known),
                self.dividend_quotient.eq(rhs.dividend_quotient)]


class FSMDivCoreStage(ControlBase):
    def __init__(self, pspec):
        super().__init__()
        self.pspec = pspec
        self.p.data_i = CoreInputData(pspec)
        self.n.data_o = CoreOutputData(pspec)
        self.saved_input_data = CoreInputData(pspec)
        self.empty = Signal(reset=1)
        self.saved_state = DivState(64, name="saved_state")
        self.div_state_next = DivStateNext(64)
        self.div_state_init = DivStateInit(64)
        self.divisor = Signal(unsigned(64))

    def elaborate(self, platform):
        m = super().elaborate(platform)
        m.submodules.div_state_next = self.div_state_next
        m.submodules.div_state_init = self.div_state_init
        data_i = self.p.data_i
        data_o = self.n.data_o
        core_i = data_i.core
        core_o = data_o.core

        core_saved_i = self.saved_input_data.core

        # TODO: handle cancellation

        m.d.comb += self.div_state_init.dividend.eq(core_i.dividend)

        m.d.comb += data_o.eq_without_core(self.saved_input_data)
        m.d.comb += core_o.quotient_root.eq(self.div_state_next.o.quotient)
        # fract width of `DivPipeCoreOutputData.remainder`
        remainder_fract_width = 64 * 3
        # fract width of `DivPipeCoreInputData.dividend`
        dividend_fract_width = 64 * 2
        rem_start = remainder_fract_width - dividend_fract_width
        m.d.comb += core_o.remainder.eq(self.div_state_next.o.remainder
                                        << rem_start)
        m.d.comb += self.n.valid_o.eq(
            ~self.empty & self.saved_state.will_be_done_after(1))
        m.d.comb += self.p.ready_o.eq(self.empty)
        m.d.sync += self.saved_state.eq(self.div_state_next.o)

        with m.If(self.empty):
            m.d.comb += self.div_state_next.i.eq(self.div_state_init.o)
            m.d.comb += self.div_state_next.divisor.eq(core_i.divisor_radicand)
            with m.If(self.p.valid_i):
                m.d.sync += self.empty.eq(0)
                m.d.sync += self.saved_input_data.eq(data_i)
        with m.Else():
            m.d.comb += [
                self.div_state_next.i.eq(self.saved_state),
                self.div_state_next.divisor.eq(core_saved_i.divisor_radicand)]
            with m.If(self.n.ready_i & self.n.valid_o):
                m.d.sync += self.empty.eq(1)

        return m

    def __iter__(self):
        yield from self.p
        yield from self.n

    def ports(self):
        return list(self)
