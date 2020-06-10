from nmigen import Signal, Const
from soc.fu.pipe_data import IntegerData
from soc.fu.alu.pipe_data import ALUOutputData, CommonPipeSpec
from soc.fu.alu.pipe_data import ALUInputData  # TODO: check this
from soc.fu.logical.logical_input_record import CompLogicalOpSubset
from ieee754.div_rem_sqrt_rsqrt.core import (
    DivPipeCoreConfig, DivPipeCoreInputData,
    DivPipeCoreInterstageData, DivPipeCoreOutputData)


class DivPipeSpec(CommonPipeSpec):
    regspec = (ALUInputData.regspec, ALUOutputData.regspec)
    opsubsetkls = CompLogicalOpSubset
    core_config = DivPipeCoreConfig(
        bit_width=64,
        fract_width=64,
        log2_radix=3,
    )


class CoreBaseData(ALUInputData):
    def __init__(self, pspec, core_data_class):
        super().__init__(pspec)
        self.core = core_data_class(pspec.core_config)
        self.divisor_neg = Signal(1, reset_less=True)
        self.dividend_neg = Signal(1, reset_less=True)

    def __iter__(self):
        yield from super().__iter__()
        yield from self.core.__iter__(self)
        yield self.divisor_neg
        yield self.dividend_neg

    def eq(self, rhs):
        return super().eq(rhs) + \
            self.core.eq(rhs.core) + \
            [self.divisor_neg.eq(rhs.divisor_neg),
             self.dividend_neg.eq(rhs.dividend_neg)]


class CoreInputData(CoreBaseData):
    def __init__(self, pspec):
        super().__init__(pspec, DivPipeCoreInputData)


class CoreInterstageData(CoreBaseData):
    def __init__(self, pspec):
        super().__init__(pspec, DivPipeCoreInterstageData)


class CoreOutputData(CoreBaseData):
    def __init__(self, pspec):
        super().__init__(pspec, DivPipeCoreOutputData)
