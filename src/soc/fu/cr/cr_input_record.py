from soc.fu.base_input_record import CompOpSubsetBase
from openpower.decoder.power_enums import (MicrOp, Function)


class CompCROpSubset(CompOpSubsetBase):
    """CompCROpSubset

    a copy of the relevant subset information from Decode2Execute1Type
    needed for CR operations.  use with eq_from_execute1 (below) to
    grab subsets.
    """
    def __init__(self, name=None):
        layout = (('insn_type', MicrOp),
                  ('fn_unit', Function),
                  ('insn', 32),
                  )

        super().__init__(layout, name=name)

