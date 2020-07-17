import enum
from nmigen import Elaboratable, Module, Signal
from soc.fu.div.pipe_data import CoreInputData, CoreOutputData


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


class FSMDivCorePrev:
    def __init__(self, pspec):
        self.data_i = CoreInputData(pspec)
        self.valid_i = Signal()
        self.ready_o = Signal()

    def __iter__(self):
        yield from self.data_i
        yield self.valid_i
        yield self.ready_o


class FSMDivCoreNext:
    def __init__(self, pspec):
        self.data_o = CoreOutputData(pspec)
        self.valid_o = Signal()
        self.ready_i = Signal()

    def __iter__(self):
        yield from self.data_o
        yield self.valid_o
        yield self.ready_i


class DivState(enum.Enum):
    Empty = 0
    Computing = 1
    WaitingOnOutput = 2


class FSMDivCoreStage(Elaboratable):
    def __init__(self, pspec):
        self.p = FSMDivCorePrev(pspec)
        self.n = FSMDivCoreNext(pspec)
        self.saved_input_data = CoreInputData(pspec)
        self.canceled = Signal()
        self.state = Signal(DivState, reset=DivState.Empty)

    def elaborate(self, platform):
        m = Module()

        # TODO: calculate self.canceled from self.p.data_i.ctx
        m.d.comb += self.canceled.eq(False)

        # TODO(programmerjake): finish

        return m

    def __iter__(self):
        yield from self.p
        yield from self.n

    def ports(self):
        return list(self)
