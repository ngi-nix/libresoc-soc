from soc.fu.base_input_record import CompOpSubsetBase
from nmigen.hdl.rec import Layout

from openpower.decoder.power_enums import MicrOp, Function, CryIn


class CompSROpSubset(CompOpSubsetBase):
    """CompSROpSubset

    a copy of the relevant subset information from Decode2Execute1Type
    needed for ALU operations.  use with eq_from_execute1 (below) to
    grab subsets.
    """
    def __init__(self, name=None):
        layout = (('insn_type', MicrOp),
                  ('fn_unit', Function),
                  ('imm_data', Layout((("data", 64), ("ok", 1)))),
                  ('rc', Layout((("rc", 1), ("ok", 1)))),
                  ('oe', Layout((("oe", 1), ("ok", 1)))),
                  ('write_cr0', 1),
                  ('invert_in', 1),
                  ('input_carry', CryIn),
                  ('output_carry', 1),
                  ('input_cr', 1),
                  ('output_cr', 1),
                  ('is_32bit', 1),
                  ('is_signed', 1),
                  ('insn', 32),
                  )

        super().__init__(layout, name=name)

