from nmigen.hdl.rec import Record, Layout

from soc.decoder.power_enums import (InternalOp, Function)


class CompSPROpSubset(Record):
    """CompSPROpSubset

    a copy of the relevant subset information from Decode2Execute1Type
    needed for TRAP operations.  use with eq_from_execute1 (below) to
    grab subsets.
    """
    def __init__(self, name=None):
        layout = (('insn_type', InternalOp),
                  ('fn_unit', Function),
                  ('insn', 32),
                  ('is_32bit', 1),
                  )

        Record.__init__(self, Layout(layout), name=name)

        # grrr.  Record does not have kwargs
        self.insn_type.reset_less = True
        self.insn.reset_less = True
        self.fn_unit.reset_less = True
        self.is_32bit.reset_less = True

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
                self.insn,
                self.fn_unit,
                self.is_32bit,
        ]