from nmigen.hdl.rec import Record, Layout

from soc.decoder.power_enums import MicrOp, Function, CryIn


class CompMULOpSubset(Record):
    """CompMULOpSubset

    a copy of the relevant subset information from Decode2Execute1Type
    needed for MUL operations.  use with eq_from_execute1 (below) to
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
                  ('is_32bit', 1),
                  ('is_signed', 1),
                  ('insn', 32),
                  )

        Record.__init__(self, Layout(layout), name=name)

        # grrr.  Record does not have kwargs
        self.insn_type.reset_less = True
        self.fn_unit.reset_less = True
        self.zero_a.reset_less = True
        self.invert_a.reset_less = True
        self.invert_out.reset_less = True
        self.is_32bit.reset_less = True
        self.is_signed.reset_less = True

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
                self.invert_a,
                self.invert_out,
                self.is_32bit,
                self.is_signed,
        ]
