from nmigen import Signal, Const
from soc.fu.pipe_data import IntegerData
from soc.fu.alu.pipe_data import ALUOutputData, CommonPipeSpec
from soc.fu.alu.pipe_data import ALUInputData # TODO: check this
from soc.fu.logical.logical_input_record import CompLogicalOpSubset


class DivPipeSpec(CommonPipeSpec):
    regspec = (ALUInputData.regspec, ALUOutputData.regspec)
    opsubsetkls = CompLogicalOpSubset
