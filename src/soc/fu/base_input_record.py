from nmigen.hdl.rec import Record, Layout
from nmigen import Signal

# needed for SVP64 information at the pipeline
from openpower.decoder.power_svp64_rm import sv_input_record_layout


class CompOpSubsetBase(Record):
    """CompOpSubsetBase

    base class of subset Operation information
    """
    def __init__(self, layout, name):
        if name is None:
            name = self.__class__.__name__
            print ("Subset name", name)
            assert name.startswith("Comp")
            assert name.endswith("OpSubset")
            name = name[4:-8].lower() + "_op"

        layout = list(layout) + sv_input_record_layout
        Record.__init__(self, Layout(layout), name=name)

        # grrr.  Record does not have kwargs
        for fname, sig in self.fields.items():
            sig.reset_less = True

    def eq_from(self, other):
        """ use this to copy in from another CompRecord
        """
        res = []
        print ("eq_from self", self, self.fields)
        print ("        other", other, other.fields)
        for fname, sig in self.fields.items():
            eqfrom = other.fields[fname]
            res.append(sig.eq(eqfrom))
        return res

    def eq_from_execute1(self, other):
        """ use this to copy in from Decode2Execute1Type
        """
        return self.eq_from(other)

    def ports(self):
        res = []
        for fname, sig in self.fields.items():
            if isinstance(sig, Signal):
                res.append(sig)
        return res
