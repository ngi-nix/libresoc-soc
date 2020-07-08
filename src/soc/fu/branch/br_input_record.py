from nmigen.hdl.rec import Record, Layout

from soc.decoder.power_enums import InternalOp, Function, CryIn


class CompBROpSubset(Record):
    """CompBROpSubset

    TODO: remove anything not needed by the Branch pipeline (determine this
    after all branch operations have been written.  see
    https://bugs.libre-soc.org/show_bug.cgi?id=313#c3)

    a copy of the relevant subset information from Decode2Execute1Type
    needed for Branch operations.  use with eq_from_execute1 (below) to
    grab subsets.
    """
    def __init__(self, name=None):
        layout = (('insn_type', InternalOp),
                  ('fn_unit', Function),
                  ('imm_data', Layout((("imm", 64), ("imm_ok", 1)))),
                  ('lk', 1),
                  ('is_32bit', 1),
                  ('insn', 32),
                  )

        Record.__init__(self, Layout(layout), name=name)

        # grrr.  Record does not have kwargs
        self.insn_type.reset_less = True
        self.fn_unit.reset_less = True
        self.lk.reset_less = True
        self.is_32bit.reset_less = True
        self.insn.reset_less = True

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
                self.fn_unit,
                self.lk,
                self.is_32bit,
                self.insn,
        ]
