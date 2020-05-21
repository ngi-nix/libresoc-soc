from nmigen.hdl.rec import Record, Layout

from soc.decoder.power_enums import InternalOp, Function, CryIn


class CompALUOpSubset(Record):
    """CompALUOpSubset

    a copy of the relevant subset information from Decode2Execute1Type
    needed for ALU operations.  use with eq_from_execute1 (below) to
    grab subsets.
    """
    def __init__(self, name=None):
        layout = (('insn_type', InternalOp),
                  ('fn_unit', Function),
                  ('imm_data', Layout((("imm", 64), ("imm_ok", 1)))),
                    #'cr = Signal(32, reset_less=True) # NO: this is from the CR SPR
                    #'xerc = XerBits() # NO: this is from the XER SPR
                  ('lk', 1),
                  ('rc', Layout((("rc", 1), ("rc_ok", 1)))),
                  ('oe', Layout((("oe", 1), ("oe_ok", 1)))),
                  ('invert_a', 1),
                  ('zero_a', 1),
                  ('invert_out', 1),
                  ('input_carry', CryIn),
                  ('output_carry', 1),
                  ('input_cr', 1),
                  ('output_cr', 1),
                  ('is_32bit', 1),
                  ('is_signed', 1),
                  ('data_len', 4), # TODO: should be in separate CompLDSTSubset
                  ('insn', 32),
                  ('byte_reverse', 1),
                  ('sign_extend', 1))

        Record.__init__(self, Layout(layout), name=name)

        # grrr.  Record does not have kwargs
        self.insn_type.reset_less = True
        self.fn_unit.reset_less = True
        #self.cr = Signal(32, reset_less = True
        #self.xerc = XerBits(
        self.lk.reset_less = True
        self.zero_a.reset_less = True
        self.invert_a.reset_less = True
        self.invert_out.reset_less = True
        self.input_carry.reset_less = True
        self.output_carry.reset_less = True
        self.input_cr.reset_less = True
        self.output_cr.reset_less = True
        self.is_32bit.reset_less = True
        self.is_signed.reset_less = True
        self.data_len.reset_less = True
        self.byte_reverse.reset_less = True
        self.sign_extend.reset_less = True

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
                #self.cr,
                #self.xerc,
                self.lk,
                self.invert_a,
                self.invert_out,
                self.input_carry,
                self.output_carry,
                self.input_cr,
                self.output_cr,
                self.is_32bit,
                self.is_signed,
                self.data_len,
                self.byte_reverse,
                self.sign_extend,
        ]
