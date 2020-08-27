# This stage is intended to handle the gating of carry and overflow
# out, summary overflow generation, and updating the condition
# register
from soc.fu.common_output_stage import CommonOutputStage
from soc.fu.shift_rot.pipe_data import (ShiftRotOutputData,
                                      ShiftRotOutputDataFinal)


class ShiftRotOutputStage(CommonOutputStage):

    def ispec(self):
        return ShiftRotOutputData(self.pspec)

    def ospec(self):
        return ShiftRotOutputDataFinal(self.pspec)

