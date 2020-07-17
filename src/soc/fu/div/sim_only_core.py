from nmigen import Signal, Elaboratable, Module
from ieee754.div_rem_sqrt_rsqrt.core import DivPipeCoreOperation


class SimOnlyCoreConfig:
    n_stages = 1
    bit_width = 64
    fract_width = 64


class SimOnlyCoreInputData:
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


class SimOnlyCoreInterstageData:
    def __init__(self, core_config, reset_less=True):
        self.core_config = core_config
        self.dividend = Signal(128, reset_less=reset_less)
        self.divisor = Signal(64, reset_less=reset_less)

    def __iter__(self):
        """ Get member signals. """
        yield self.dividend
        yield self.divisor

    def eq(self, rhs):
        """ Assign member signals. """
        return [self.dividend.eq(rhs.dividend),
                self.divisor.eq(rhs.divisor)]


class SimOnlyCoreOutputData:
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


class SimOnlyCoreSetupStage(Elaboratable):
    def __init__(self, core_config):
        self.core_config = core_config
        self.i = self.ispec()
        self.o = self.ospec()

    def ispec(self):
        """ Get the input spec for this pipeline stage."""
        return SimOnlyCoreInputData(self.core_config)

    def ospec(self):
        """ Get the output spec for this pipeline stage."""
        return SimOnlyCoreInterstageData(self.core_config)

    def setup(self, m, i):
        """ Pipeline stage setup. """
        m.submodules.sim_only_core_setup = self
        m.d.comb += self.i.eq(i)

    def process(self, i):
        """ Pipeline stage process. """
        return self.o  # return processed data (ignore i)

    def elaborate(self, platform):
        """ Elaborate into ``Module``. """
        m = Module()
        comb = m.d.comb

        comb += self.o.divisor.eq(self.i.divisor_radicand)
        comb += self.o.dividend.eq(self.i.dividend)

        return m


class SimOnlyCoreCalculateStage(Elaboratable):
    def __init__(self, core_config, stage_index):
        assert stage_index == 0
        self.core_config = core_config
        self.stage_index = stage_index
        self.i = self.ispec()
        self.o = self.ospec()

    def ispec(self):
        """ Get the input spec for this pipeline stage. """
        return SimOnlyCoreInterstageData(self.core_config)

    def ospec(self):
        """ Get the output spec for this pipeline stage. """
        return SimOnlyCoreInterstageData(self.core_config)

    def setup(self, m, i):
        """ Pipeline stage setup. """
        setattr(m.submodules,
                f"sim_only_core_calculate_{self.stage_index}",
                self)
        m.d.comb += self.i.eq(i)

    def process(self, i):
        """ Pipeline stage process. """
        return self.o

    def elaborate(self, platform):
        """ Elaborate into ``Module``. """
        m = Module()
        m.d.comb += self.o.eq(self.i)
        return m


class SimOnlyCoreFinalStage(Elaboratable):
    """ Final Stage of the core of the div/rem/sqrt/rsqrt pipeline. """

    def __init__(self, core_config):
        """ Create a ``SimOnlyCoreFinalStage`` instance."""
        self.core_config = core_config
        self.i = self.ispec()
        self.o = self.ospec()

    def ispec(self):
        """ Get the input spec for this pipeline stage."""
        return SimOnlyCoreInterstageData(self.core_config)

    def ospec(self):
        """ Get the output spec for this pipeline stage."""
        return SimOnlyCoreOutputData(self.core_config)

    def setup(self, m, i):
        """ Pipeline stage setup. """
        m.submodules.sim_only_core_final = self
        m.d.comb += self.i.eq(i)

    def process(self, i):
        """ Pipeline stage process. """
        return self.o  # return processed data (ignore i)

    def elaborate(self, platform):
        """ Elaborate into ``Module``. """
        m = Module()
        remainder_shift = self.core_config.fract_width
        with m.If(self.i.divisor != 0):
            quotient = self.i.dividend // self.i.divisor
            remainder = self.i.dividend % self.i.divisor
            m.d.comb += self.o.quotient_root.eq(quotient)
            m.d.comb += self.o.remainder.eq(remainder << remainder_shift)
        with m.Else():
            m.d.comb += self.o.quotient_root.eq(-1)
            m.d.comb += self.o.remainder.eq(self.i.dividend << remainder_shift)

        return m
