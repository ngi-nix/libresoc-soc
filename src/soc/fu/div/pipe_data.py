from nmigen import Signal, Const
from soc.fu.pipe_data import IntegerData
from soc.fu.alu.pipe_data import ALUOutputData, CommonPipeSpec
from soc.fu.logical.pipe_data import LogicalInputData
from soc.fu.logical.logical_input_record import CompLogicalOpSubset


class DivPipeSpec(CommonPipeSpec):
    regspec = (LogicalInputData.regspec, ALUOutputData.regspec)
    opsubsetkls = CompLogicalOpSubset
