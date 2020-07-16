from nmigen.hdl.rec import Record, Layout
from nmigen import Signal


class CompOpSubsetBase(Record):
    """CompOpSubsetBase

    base class of subset Operation information
    """
    def __init__(self, layout, name):

        Record.__init__(self, Layout(layout), name=name)

        # grrr.  Record does not have kwargs
        for fname, sig in self.fields.items():
            sig.reset_less = True

    def eq_from_execute1(self, other):
        """ use this to copy in from Decode2Execute1Type
        """
        res = []
        for fname, sig in self.fields.items():
            eqfrom = other.do.fields[fname]
            res.append(sig.eq(eqfrom))
        return res

    def ports(self):
        res = []
        for fname, sig in self.fields.items():
            if isinstance(sig, Signal):
                res.append(sig)
        return res