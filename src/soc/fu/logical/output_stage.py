# This stage is intended to handle the gating of carry and overflow
# out, summary overflow generation, and updating the condition
# register
from nmigen import (Module, Signal, Cat, Repl)
from nmutil.pipemodbase import PipeModBase
from soc.fu.common_output_stage import CommonOutputStage
from soc.fu.logical.pipe_data import LogicalInputData, LogicalOutputData
from ieee754.part.partsig import PartitionedSignal
from soc.decoder.power_enums import MicrOp


class LogicalOutputStage(CommonOutputStage):

    def ispec(self):
        return LogicalOutputData(self.pspec)

    def ospec(self):
        return LogicalOutputData(self.pspec)

