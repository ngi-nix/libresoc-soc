import enum
from nmigen import Signal, Const
from soc.fu.pipe_data import FUBaseData
from soc.fu.alu.pipe_data import CommonPipeSpec
from soc.fu.logical.logical_input_record import CompLogicalOpSubset
from ieee754.div_rem_sqrt_rsqrt.core import (
    DivPipeCoreConfig, DivPipeCoreInputData, DP,
    DivPipeCoreInterstageData, DivPipeCoreOutputData,
    DivPipeCoreSetupStage, DivPipeCoreCalculateStage, DivPipeCoreFinalStage)


class DivInputData(FUBaseData):
    regspec = [('INT', 'ra', '0:63'),  # RA
               ('INT', 'rb', '0:63'),  # RB/immediate
               ('XER', 'xer_so', '32'), ]  # XER bit 32: SO

    def __init__(self, pspec):
        super().__init__(pspec, False)
        # convenience
        self.a, self.b = self.ra, self.rb


# output stage shared between div and mul: like ALUOutputData but no CA/32
class DivMulOutputData(FUBaseData):
    regspec = [('INT', 'o', '0:63'),
               ('CR', 'cr_a', '0:3'),
               ('XER', 'xer_ov', '33,44'),  # bit0: ov, bit1: ov32
               ('XER', 'xer_so', '32')]

    def __init__(self, pspec):
        super().__init__(pspec, True)
        # convenience
        self.cr0 = self.cr_a


class DivPipeKindConfigBase:
    def __init__(self,
                 core_config,
                 core_input_data_class,
                 core_interstage_data_class,
                 core_output_data_class):
        self.core_config = core_config
        self.core_input_data_class = core_input_data_class
        self.core_interstage_data_class = core_interstage_data_class
        self.core_output_data_class = core_output_data_class


class DivPipeKindConfigCombPipe(DivPipeKindConfigBase):
    def __init__(self,
                 core_config,
                 core_input_data_class,
                 core_interstage_data_class,
                 core_output_data_class,
                 core_setup_stage_class,
                 core_calculate_stage_class,
                 core_final_stage_class):
        super().__init__(core_config, core_input_data_class,
                         core_interstage_data_class, core_output_data_class)
        self.core_setup_stage_class = core_setup_stage_class
        self.core_calculate_stage_class = core_calculate_stage_class
        self.core_final_stage_class = core_final_stage_class


class DivPipeKindConfigFSM(DivPipeKindConfigBase):
    def __init__(self,
                 core_config,
                 core_input_data_class,
                 core_output_data_class,
                 core_stage_class):
        core_interstage_data_class = None
        super().__init__(core_config, core_input_data_class,
                         core_interstage_data_class, core_output_data_class)
        self.core_stage_class = core_stage_class


class DivPipeKind(enum.Enum):
    # use ieee754.div_rem_sqrt_rsqrt.core.DivPipeCore*
    DivPipeCore = enum.auto()
    # use nmigen's built-in div and rem operators -- only suitable for
    # simulation
    SimOnly = enum.auto()
    # use a FSM-based div core
    FSMDivCore = enum.auto()

    @property
    def config(self):
        if self == DivPipeKind.DivPipeCore:
            return DivPipeKindConfigCombPipe(
                core_config=DivPipeCoreConfig(
                    bit_width=64,
                    fract_width=64,
                    log2_radix=1,
                    supported=[DP.UDivRem]
                ),
                core_input_data_class=DivPipeCoreInputData,
                core_interstage_data_class=DivPipeCoreInterstageData,
                core_output_data_class=DivPipeCoreOutputData,
                core_setup_stage_class=DivPipeCoreSetupStage,
                core_calculate_stage_class=DivPipeCoreCalculateStage,
                core_final_stage_class=DivPipeCoreFinalStage)
        if self == DivPipeKind.SimOnly:
            # import here to avoid import loop
            from soc.fu.div.sim_only_core import (
                SimOnlyCoreConfig, SimOnlyCoreInputData,
                SimOnlyCoreInterstageData, SimOnlyCoreOutputData,
                SimOnlyCoreSetupStage, SimOnlyCoreCalculateStage,
                SimOnlyCoreFinalStage)
            return DivPipeKindConfigCombPipe(
                core_config=SimOnlyCoreConfig(),
                core_input_data_class=SimOnlyCoreInputData,
                core_interstage_data_class=SimOnlyCoreInterstageData,
                core_output_data_class=SimOnlyCoreOutputData,
                core_setup_stage_class=SimOnlyCoreSetupStage,
                core_calculate_stage_class=SimOnlyCoreCalculateStage,
                core_final_stage_class=SimOnlyCoreFinalStage)
        # ensure we didn't forget any cases
        # -- I wish Python had a switch/match statement
        assert self == DivPipeKind.FSMDivCore

        # import here to avoid import loop
        from soc.fu.div.fsm import (
            FSMDivCoreConfig, FSMDivCoreInputData,
            FSMDivCoreOutputData, FSMDivCoreStage)
        return DivPipeKindConfigFSM(
            core_config=FSMDivCoreConfig(),
            core_input_data_class=FSMDivCoreInputData,
            core_output_data_class=FSMDivCoreOutputData,
            core_stage_class=FSMDivCoreStage)


class DivPipeSpec(CommonPipeSpec):
    def __init__(self, id_wid, div_pipe_kind):
        super().__init__(id_wid=id_wid)
        self.div_pipe_kind = div_pipe_kind
        self.core_config = div_pipe_kind.config.core_config

    regspec = (DivInputData.regspec, DivMulOutputData.regspec)
    opsubsetkls = CompLogicalOpSubset


class DivPipeSpecDivPipeCore(DivPipeSpec):
    def __init__(self, id_wid):
        super().__init__(id_wid=id_wid, div_pipe_kind=DivPipeKind.DivPipeCore)


class DivPipeSpecFSMDivCore(DivPipeSpec):
    def __init__(self, id_wid):
        super().__init__(id_wid=id_wid, div_pipe_kind=DivPipeKind.FSMDivCore)


class DivPipeSpecSimOnly(DivPipeSpec):
    def __init__(self, id_wid):
        super().__init__(id_wid=id_wid, div_pipe_kind=DivPipeKind.SimOnly)


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
        super().__init__(pspec,
                         pspec.div_pipe_kind.config.core_input_data_class)


class CoreInterstageData(CoreBaseData):
    def __init__(self, pspec):
        data_class = pspec.div_pipe_kind.config.core_interstage_data_class
        if data_class is None:
            raise ValueError(
                f"CoreInterstageData not supported for {pspec.div_pipe_kind}")
        super().__init__(pspec, data_class)


class CoreOutputData(CoreBaseData):
    def __init__(self, pspec):
        super().__init__(pspec,
                         pspec.div_pipe_kind.config.core_output_data_class)
