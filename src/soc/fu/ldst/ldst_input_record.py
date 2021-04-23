from soc.fu.base_input_record import CompOpSubsetBase
from nmigen.hdl.rec import Layout

from openpower.decoder.power_enums import MicrOp, Function, LDSTMode


class CompLDSTOpSubset(CompOpSubsetBase):
    """CompLDSTOpSubset

    a copy of the relevant subset information from Decode2Execute1Type
    needed for LD/ST operations.  use with eq_from_execute1 (below) to
    grab subsets.

    note: rc / oe is needed (later) for st*cx when it comes to setting OV/SO
    """
    def __init__(self, name=None):
        layout = (('insn_type', MicrOp),
                  ('fn_unit', Function),
                  ('imm_data', Layout((("data", 64), ("ok", 1)))),
                  ('zero_a', 1),
                  ('rc', Layout((("rc", 1), ("ok", 1)))), # for later
                  ('oe', Layout((("oe", 1), ("ok", 1)))), # for later
                  ('is_32bit', 1),
                  ('is_signed', 1),
                  ('data_len', 4),
                  ('byte_reverse', 1),
                  ('sign_extend', 1),
                  ('ldst_mode', LDSTMode),
                  ('insn', 32),
                 )

        super().__init__(layout, name=name)

