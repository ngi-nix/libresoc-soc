from soc.fu.base_input_record import CompOpSubsetBase
from nmigen.hdl.rec import Layout

from soc.decoder.power_enums import MicrOp, Function, LDSTMode


class CompLDSTOpSubset(CompOpSubsetBase):
    """CompLDSTOpSubset

    a copy of the relevant subset information from Decode2Execute1Type
    needed for LD/ST operations.  use with eq_from_execute1 (below) to
    grab subsets.

    note: rc / oe is needed (later) for st*cx when it comes to setting OV/SO
    """
    def __init__(self, name=None):
        layout = (('insn_type', MicrOp),
                  ('imm_data', Layout((("imm", 64), ("imm_ok", 1)))),
                  ('zero_a', 1),
                  ('rc', Layout((("rc", 1), ("rc_ok", 1)))), # for later
                  ('oe', Layout((("oe", 1), ("oe_ok", 1)))), # for later
                  ('is_32bit', 1),
                  ('is_signed', 1),
                  ('data_len', 4),
                  ('byte_reverse', 1),
                  ('sign_extend', 1),
                  ('ldst_mode', LDSTMode))

        super().__init__(layout, name=name)

