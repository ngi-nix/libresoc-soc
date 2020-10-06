from soc.fu.base_input_record import CompOpSubsetBase
from soc.decoder.power_enums import (MicrOp, Function)
from soc.consts import TT
from soc.experiment.mem_types import LDSTException

class CompTrapOpSubset(CompOpSubsetBase):
    """CompTrapOpSubset

    a copy of the relevant subset information from Decode2Execute1Type
    needed for TRAP operations.  use with eq_from_execute1 (below) to
    grab subsets.
    """
    def __init__(self, name=None):
        layout = [('insn_type', MicrOp),
                  ('fn_unit', Function),
                  ('insn', 32),
                  ('msr', 64), # TODO: "state" in separate Record
                  ('cia', 64), # likewise
                  ('is_32bit', 1),
                  ('traptype', TT.size), # see trap main_stage.py, PowerDecoder2
                  ('trapaddr', 13),
                  ]

        # add LDST field exception types
        #for f in LDSTException._exc_types:
        #    layout.append((f, 1))

        super().__init__(layout, name=name)

