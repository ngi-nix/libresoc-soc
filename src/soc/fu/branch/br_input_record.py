from soc.fu.base_input_record import CompOpSubsetBase
from nmigen.hdl.rec import Layout

from openpower.decoder.power_enums import MicrOp, Function


class CompBROpSubset(CompOpSubsetBase):
    """CompBROpSubset

    a copy of the relevant subset information from Decode2Execute1Type
    needed for Branch operations.  use with eq_from_execute1 (below) to
    grab subsets.
    """
    def __init__(self, name=None):
        layout = (('cia', 64), # PC "state"
                  ('insn_type', MicrOp),
                  ('fn_unit', Function),
                  ('insn', 32),
                  ('imm_data', Layout((("data", 64), ("ok", 1)))),
                  ('lk', 1),
                  ('is_32bit', 1),
                  )

        super().__init__(layout, name=name)

