from nmigen.hdl.rec import Record, Layout

from soc.decoder.power_enums import InternalOp, Function, CryIn


class CompSROpSubset(Record):
    """CompSROpSubset

    a copy of the relevant subset information from Decode2Execute1Type
    needed for ALU operations.  use with eq_from_execute1 (below) to
    grab subsets.
    """
    def __init__(self, name=None):
        layout = (('insn_type', InternalOp),
                  ('fn_unit', Function),
                  ('imm_data', Layout((("imm", 64), ("imm_ok", 1)))),
                  ('rc', Layout((("rc", 1), ("rc_ok", 1)))),
                  ('oe', Layout((("oe", 1), ("oe_ok", 1)))),
                  ('write_cr0', 0),
                  ('input_carry', CryIn),
                  ('output_carry', 1),
                  ('input_cr', 1),
                  ('output_cr', 1),
                  ('is_32bit', 1),
                  ('is_signed', 1),
                  ('insn', 32),
                  )

        Record.__init__(self, Layout(layout), name=name)

        # grrr.  Record does not have kwargs
        self.insn_type.reset_less = True
        self.fn_unit.reset_less = True
        self.input_carry.reset_less = True
        self.output_carry.reset_less = True
        self.input_cr.reset_less = True
        self.output_cr.reset_less = True
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
                self.input_carry,
                self.output_carry,
                self.input_cr,
                self.output_cr,
                self.is_32bit,
                self.is_signed,
        ]
