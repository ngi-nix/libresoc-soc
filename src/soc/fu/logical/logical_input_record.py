from nmigen.hdl.rec import Record, Layout

from soc.decoder.power_enums import InternalOp, Function, CryIn


class CompLogicalOpSubset(Record):
    """CompLogicalOpSubset

    a copy of the relevant subset information from Decode2Execute1Type
    needed for Logical operations.  use with eq_from_execute1 (below) to
    grab subsets.
    """
    def __init__(self, name=None):
        layout = (('insn_type', InternalOp),
                  ('fn_unit', Function),
                  ('imm_data', Layout((("imm", 64), ("imm_ok", 1)))),
                  ('lk', 1),
                  ('rc', Layout((("rc", 1), ("rc_ok", 1)))),
                  ('oe', Layout((("oe", 1), ("oe_ok", 1)))),
                  ('invert_a', 1),
                  ('zero_a', 1),
                  ('input_carry', CryIn),
                  ('invert_out', 1),
                  ('output_carry', 1),
                  ('is_32bit', 1),
                  ('is_signed', 1),
                  ('data_len', 4),
                  ('insn', 32),
                  )

        Record.__init__(self, Layout(layout), name=name)

        # grrr.  Record does not have kwargs
        self.insn_type.reset_less = True
        self.fn_unit.reset_less = True
        self.lk.reset_less = True
        self.zero_a.reset_less = True
        self.invert_a.reset_less = True
        self.invert_out.reset_less = True
        self.input_carry.reset_less = True
        self.output_carry.reset_less = True
        self.is_32bit.reset_less = True
        self.is_signed.reset_less = True
        self.data_len.reset_less = True

    def eq_from_execute1(self, other):
        """ use this to copy in from Decode2Execute1Type
        """
        res = []
        for fname, sig in self.fields.items():
            eqfrom = other.fields[fname]
            res.append(sig.eq(eqfrom))
        return res

    def ports(self):
        return [self.insn_type,
                self.fn_unit,
                self.lk,
                self.invert_a,
                self.invert_out,
                self.input_carry,
                self.output_carry,
                self.is_32bit,
                self.is_signed,
                self.data_len,
        ]
