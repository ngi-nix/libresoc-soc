from nmigen.hdl.rec import Record, Layout

from soc.decoder.power_enums import MicrOp, Function, LDSTMode


class CompLDSTOpSubset(Record):
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

        Record.__init__(self, Layout(layout), name=name)

        # grrr.  Record does not have kwargs
        self.insn_type.reset_less = True
        self.is_32bit.reset_less = True
        self.zero_a.reset_less = True
        self.is_signed.reset_less = True
        self.data_len.reset_less = True
        self.byte_reverse.reset_less = True
        self.sign_extend.reset_less = True
        self.ldst_mode.reset_less = True

    def eq_from_execute1(self, other):
        """ use this to copy in from Decode2Execute1Type
        """
        res = []
        for fname, sig in self.fields.items():
            eqfrom = other.do.fields[fname]
            res.append(sig.eq(eqfrom))
        return res

    def ports(self):
        return [self.insn_type,
                self.is_32bit,
                self.zero_a,
                self.is_signed,
                self.data_len,
                self.byte_reverse,
                self.sign_extend,
                self.ldst_mode,
        ]

