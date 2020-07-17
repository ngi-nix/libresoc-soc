from nmigen import Signal, Const
from soc.fu.pipe_data import IntegerData
from soc.fu.alu.pipe_data import CommonPipeSpec
from soc.fu.logical.logical_input_record import CompLogicalOpSubset
from ieee754.div_rem_sqrt_rsqrt.core import (
    DivPipeCoreConfig, DivPipeCoreInputData, DP,
    DivPipeCoreInterstageData, DivPipeCoreOutputData)


class DivInputData(IntegerData):
    regspec = [('INT', 'ra', '0:63'),  # RA
               ('INT', 'rb', '0:63'),  # RB/immediate
               ('XER', 'xer_so', '32'), ]  # XER bit 32: SO

    def __init__(self, pspec):
        super().__init__(pspec, False)
        # convenience
        self.a, self.b = self.ra, self.rb


# output stage shared between div and mul: like ALUOutputData but no CA/32
class DivMulOutputData(IntegerData):
    regspec = [('INT', 'o', '0:63'),
               ('CR', 'cr_a', '0:3'),
               ('XER', 'xer_ov', '33,44'),  # bit0: ov, bit1: ov32
               ('XER', 'xer_so', '32')]

    def __init__(self, pspec):
        super().__init__(pspec, True)
        # convenience
        self.cr0 = self.cr_a


class DivPipeSpec(CommonPipeSpec):
    regspec = (DivInputData.regspec, DivMulOutputData.regspec)
    opsubsetkls = CompLogicalOpSubset
    core_config = DivPipeCoreConfig(
        bit_width=64,
        fract_width=64,
        log2_radix=1,
        supported=[DP.UDivRem]
    )


class CoreBaseData(DivInputData):
    def __init__(self, pspec, core_data_class):
        super().__init__(pspec)
        self.core = core_data_class(pspec.core_config)
        self.divisor_neg = Signal(reset_less=True)
        self.dividend_neg = Signal(reset_less=True)
        self.div_by_zero = Signal(reset_less=True)

        # set if an overflow for divide extended instructions is detected
        # because `abs_dividend >= abs_divisor` for the appropriate bit width;
        # 0 if the instruction is not a divide extended instruction
        self.dive_abs_ov32 = Signal(reset_less=True)
        self.dive_abs_ov64 = Signal(reset_less=True)

    def __iter__(self):
        yield from super().__iter__()
        yield from self.core.__iter__(self)
        yield self.divisor_neg
        yield self.dividend_neg

    def eq(self, rhs):
        return self.eq_without_core(rhs) + self.core.eq(rhs.core)

    def eq_without_core(self, rhs):
        return super().eq(rhs) + \
            [self.divisor_neg.eq(rhs.divisor_neg),
             self.dividend_neg.eq(rhs.dividend_neg),
             self.dive_abs_ov32.eq(rhs.dive_abs_ov32),
             self.dive_abs_ov64.eq(rhs.dive_abs_ov64),
             self.div_by_zero.eq(rhs.div_by_zero)]


class CoreInputData(CoreBaseData):
    def __init__(self, pspec):
        super().__init__(pspec, DivPipeCoreInputData)


class CoreInterstageData(CoreBaseData):
    def __init__(self, pspec):
        super().__init__(pspec, DivPipeCoreInterstageData)


class CoreOutputData(CoreBaseData):
    def __init__(self, pspec):
        super().__init__(pspec, DivPipeCoreOutputData)
