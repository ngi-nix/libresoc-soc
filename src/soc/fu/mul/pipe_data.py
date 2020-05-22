from soc.fu.alu.alu_input_record import CompALUOpSubset
from soc.fu.pipe_data import IntegerData, CommonPipeSpec
from soc.fu.alu.pipe_data import ALUOutputData
from soc.fu.shift_rot.pipe_data import ShoftRotInputData


# TODO: replace CompALUOpSubset with CompShiftRotOpSubset
class ShiftRotPipeSpec(CommonPipeSpec):
    regspec = (ShiftRotInputData.regspec, ALUOutputData.regspec)
    opsubsetkls = CompALUOpSubset
