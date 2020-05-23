"""
* see https://libre-soc.org/3d_gpu/architecture/regfile/ section on regspecs

"""

from nmigen.cli import rtlil
from soc.experiment.compalu_multi import MultiCompUnit

from soc.fu.alu.pipeline import ALUBasePipe
from soc.fu.alu.pipe_data import ALUPipeSpec

from soc.fu.cr.pipeline import CRBasePipe
from soc.fu.cr.pipe_data import CRPipeSpec


class FunctionUnitBaseSingle(MultiCompUnit):
    """FunctionUnitBaseSingle

    main "glue" class that brings everything together.
    ONLY use this class for single-stage pipelines.

    * :speckls:  - the specification.  contains regspec and op subset info,
                   and contains common "stuff" like the pipeline ctx,
                   what type of nmutil pipeline base is to be used (etc)
    * :pipekls:  - the type of pipeline.  actually connects things together

    note that it is through MultiCompUnit.get_in/out that we *actually*
    connect up the association between regspec variable names (defined
    in the pipe_data).
    """
    def __init__(self, speckls, pipekls):
        pspec = speckls(id_wid=2)                # spec (NNNPipeSpec instance)
        opsubset = pspec.opsubsetkls             # get the operand subset class
        regspec = pspec.regspec                  # get the regspec
        alu = pipekls(pspec)                     # create actual NNNBasePipe
        super().__init__(regspec, alu, opsubset) # pass to MultiCompUnit


######################################################################
###### actual Function Units: these are "single" stage pipelines #####

class ALUFunctionUnit(FunctionUnitBaseSingle):
    def __init__(self): super().__init__(ALUPipeSpec, ALUBasePipe)

class CRFunctionUnit(FunctionUnitBaseSingle):
    def __init__(self): super().__init__(CRPipeSpec, CRBasePipe)

#####################################################################
###### actual Function Units: these are "multi" stage pipelines #####

# TODO: ReservationStations-based.


def tst_single_fus_il():
    for (name, kls) in (('alu', ALUFunctionUnit),
                        ('cr', CRFunctionUnit)):
        fu = kls()
        vl = rtlil.convert(fu, ports=fu.ports())
        with open("fu_%s.il" % name, "w") as f:
            f.write(vl)

if __name__ == '__main__':
    tst_single_fus_il()
