from soc.fu.base_input_record import CompOpSubsetBase
from soc.decoder.power_enums import (MicrOp, Function)


class CompTrapOpSubset(CompOpSubsetBase):
    """CompTrapOpSubset

    a copy of the relevant subset information from Decode2Execute1Type
    needed for TRAP operations.  use with eq_from_execute1 (below) to
    grab subsets.
    """
    def __init__(self, name=None):
        layout = (('insn_type', MicrOp),
                  ('fn_unit', Function),
                  ('insn', 32),
                  ('is_32bit', 1),
                  ('traptype', 5), # see trap main_stage.py and PowerDecoder2
                  ('trapaddr', 13),
                  )

        super().__init__(layout, name=name)

