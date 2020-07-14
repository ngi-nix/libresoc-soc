from soc.fu.base_input_record import CompOpSubsetBase
from soc.decoder.power_enums import MicrOp, Function, CryIn
from nmigen.hdl.rec import Layout


class CompALUOpSubset(CompOpSubsetBase):
    """CompALUOpSubset

    a copy of the relevant subset information from Decode2Execute1Type
    needed for ALU operations.  use with eq_from_execute1 (below) to
    grab subsets.
    """
    def __init__(self, name=None):
        layout = (('insn_type', MicrOp),
                  ('fn_unit', Function),
                  ('imm_data', Layout((("imm", 64), ("imm_ok", 1)))),
                  ('rc', Layout((("rc", 1), ("rc_ok", 1)))), # Data
                  ('oe', Layout((("oe", 1), ("oe_ok", 1)))), # Data
                  ('invert_a', 1),
                  ('zero_a', 1),
                  ('invert_out', 1),
                  ('write_cr0', 1),
                  ('input_carry', CryIn),
                  ('output_carry', 1),
                  ('is_32bit', 1),
                  ('is_signed', 1),
                  ('data_len', 4), # actually used by ALU, in OP_EXTS
                  ('insn', 32),
                  )
        super().__init__(layout, name=name)

