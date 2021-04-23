# This stage is the setup stage that converts the inputs
# into the values expected by DivPipeCore

from nmigen import (Module, Signal, Cat, Repl, Mux, Const, Array)
from nmutil.pipemodbase import PipeModBase
from ieee754.part.partsig import PartitionedSignal
from openpower.decoder.power_enums import MicrOp

from openpower.decoder.power_fields import DecodeFields
from openpower.decoder.power_fieldsn import SignalBitRange
from soc.fu.div.pipe_data import (CoreInputData,
                                  CoreInterstageData,
                                  CoreOutputData)
from ieee754.div_rem_sqrt_rsqrt.core import (DivPipeCoreSetupStage,
                                             DivPipeCoreCalculateStage,
                                             DivPipeCoreFinalStage)

__all__ = ["DivCoreBaseStage", "DivCoreSetupStage",
           "DivCoreCalculateStage", "DivCoreFinalStage"]


class DivCoreBaseStage(PipeModBase):
    def __init__(self, pspec, modname, core_class, *args, **kwargs):
        super().__init__(pspec, modname)
        self.core = core_class(pspec.core_config, *args, **kwargs)

    def elaborate(self, platform):
        m = Module()

        # pass-through on non-core parameters
        m.d.comb += self.o.eq_without_core(self.i)

        m.submodules.core = self.core

        # copy parameters to/from divremsqrt core into the Base, here.
        m.d.comb += self.core.i.eq(self.i.core)
        m.d.comb += self.o.core.eq(self.core.o)

        return m


class DivCoreSetupStage(DivCoreBaseStage):
    def __init__(self, pspec):
        super().__init__(pspec, "core_setup_stage",
                         pspec.div_pipe_kind.config.core_setup_stage_class)

    def ispec(self):
        return CoreInputData(self.pspec)

    def ospec(self):
        return CoreInterstageData(self.pspec)


class DivCoreCalculateStage(DivCoreBaseStage):
    def __init__(self, pspec, stage_index):
        stage = pspec.div_pipe_kind.config.core_calculate_stage_class
        super().__init__(pspec, f"core_calculate_stage_{stage_index}",
                         stage, stage_index)

    def ispec(self):
        return CoreInterstageData(self.pspec)

    def ospec(self):
        return CoreInterstageData(self.pspec)


class DivCoreFinalStage(DivCoreBaseStage):
    def __init__(self, pspec):
        super().__init__(pspec, "core_final_stage",
                         pspec.div_pipe_kind.config.core_final_stage_class)

    def ispec(self):
        return CoreInterstageData(self.pspec)

    def ospec(self):
        return CoreOutputData(self.pspec)
