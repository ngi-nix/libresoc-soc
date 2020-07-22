import enum
from nmigen import Elaboratable, Module, Signal, Shape, unsigned, Cat, Mux
from soc.fu.div.pipe_data import CoreInputData, CoreOutputData, DivPipeSpec
from nmutil.iocontrol import PrevControl, NextControl
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


class FSMDivCorePrevControl(PrevControl):
    data_i: CoreInputData

    def __init__(self, pspec):
        super().__init__(stage_ctl=True, maskwid=pspec.id_wid)
        self.pspec = pspec
        self.data_i = CoreInputData(pspec)


class FSMDivCoreNextControl(NextControl):
    data_o: CoreOutputData

    def __init__(self, pspec):
        super().__init__(stage_ctl=True, maskwid=pspec.id_wid)
        self.pspec = pspec
        self.data_o = CoreOutputData(pspec)


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
        return self.q_bits_known == self.quotient_width

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


class FSMDivCoreStage(Elaboratable):
    def __init__(self, pspec: DivPipeSpec):
        self.pspec = pspec
        self.p = FSMDivCorePrevControl(pspec)
        self.n = FSMDivCoreNextControl(pspec)
        self.saved_input_data = CoreInputData(pspec)
        self.canceled = Signal()
        self.empty = Signal(reset=1)
        self.saved_state = DivState(64, name="saved_state")
        self.div_state_next = DivStateNext(64)
        self.div_state_init = DivStateInit(64)
        self.divisor = Signal(unsigned(64))

    def elaborate(self, platform):
        m = Module()
        m.submodules.p = self.p
        m.submodules.n = self.n
        m.submodules.div_state_next = self.div_state_next
        m.submodules.div_state_init = self.div_state_init
        data_i = self.p.data_i
        core_i: FSMDivCoreInputData = data_i.core
        data_o = self.n.data_o
        core_o: FSMDivCoreOutputData = data_o.core

        # TODO: calculate self.canceled from self.p.data_i.ctx
        m.d.comb += self.canceled.eq(False)

        m.d.comb += self.div_state_init.dividend.eq(core_i.dividend)

        # FIXME(programmerjake): finish
        raise NotImplementedError()
        with m.If(self.canceled):
            with m.If(self.p.valid_i):
                ...
            with m.Else():
                ...
        with m.Else():
            with m.If(self.p.valid_i):
                ...
            with m.Else():
                ...

        return m

    def __iter__(self):
        yield from self.p
        yield from self.n

    def ports(self):
        return list(self)
