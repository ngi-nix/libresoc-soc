"""Cascading Power ISA Decoder

License: LGPLv3

# Copyright (C) 2020 Luke Kenneth Casson Leighton <lkcl@lkcl.net>
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>

This module uses CSV tables in a hierarchical/peer cascading fashion,
to create a multi-level instruction decoder by recognising appropriate
patterns.  The output is a wide, flattened (1-level) series of bitfields,
suitable for a simple RISC engine.

This is based on Anton Blanchard's excellent microwatt work:
https://github.com/antonblanchard/microwatt/blob/master/decode1.vhdl

The basic principle is that the python code does the heavy lifting
(reading the CSV files, constructing the hierarchy), creating the HDL
AST with for-loops generating switch-case statements.

Where "normal" HDL would do this, in laborious excruciating detail:

    switch (opcode & major_mask_bits):
        case opcode_2: decode_opcode_2()
        case opcode_19:
                switch (opcode & minor_19_mask_bits)
                    case minor_opcode_19_operation_X:
                    case minor_opcode_19_operation_y:

we take *full* advantage of the decoupling between python and the
nmigen AST data structure, to do this:

    with m.Switch(opcode & self.mask):
        for case_bitmask in subcases:
            with m.If(opcode & case_bitmask): {do_something}

this includes specifying the information sufficient to perform subdecoding.

create_pdecode()

    the full hierarchical tree for decoding POWER9 is specified here
    subsetting is possible by specifying col_subset (row_subset TODO)

PowerDecoder

    takes a *list* of CSV files with an associated bit-range that it
    is requested to match against the "opcode" row of the CSV file.
    This pattern can be either an integer, a binary number, *or* a
    wildcard nmigen Case pattern of the form "001--1-100".

Subdecoders

    these are *additional* cases with further decoding.  The "pattern"
    argument is specified as one of the Case statements (a peer of the
    opcode row in the CSV file), and thus further fields of the opcode
    may be decoded giving increasing levels of detail.

Top Level:

    [ (extra.csv: bit-fields entire 32-bit range
        opcode                           -> matches
        000000---------------01000000000 -> ILLEGAL instruction
        01100000000000000000000000000000 -> SIM_CONFIG instruction
        ................................ ->
      ),
      (major.csv: first 6 bits ONLY
        opcode                           -> matches
        001100                           -> ALU,OP_ADD (add)
        001101                           -> ALU,OP_ADD (another type of add)
        ......                           -> ...
        ......                           -> ...
        subdecoders:
        001011 this must match *MAJOR*.CSV
            [ (minor_19.csv: bits 21 through 30 inclusive:
                opcode                  -> matches
                0b0000000000            -> ALU,OP_MCRF
                ............            -> ....
              ),
              (minor_19_00000.csv: bits 21 through 25 inclusive:
                opcode                  -> matches
                0b00010                 -> ALU,add_pcis
              )
            ]
      ),
    ]


"""

from collections import namedtuple
from nmigen import Module, Elaboratable, Signal, Cat, Mux
from nmigen.cli import rtlil
from soc.decoder.power_enums import (Function, Form, MicrOp,
                                     In1Sel, In2Sel, In3Sel, OutSel,
                                     RC, LdstLen, LDSTMode, CryIn, get_csv,
                                     single_bit_flags, CRInSel,
                                     CROutSel, get_signal_name,
                                     default_values, insns, asmidx)
from soc.decoder.power_fields import DecodeFields
from soc.decoder.power_fieldsn import SigDecode, SignalBitRange


# key data structure in which the POWER decoder is specified,
# in a hierarchical fashion
Subdecoder = namedtuple("Subdecoder",
    ["pattern",    # the major pattern to search for (e.g. major opcode)
     "opcodes",    # a dictionary of minor patterns to find
     "opint",      # true => the pattern must not be in "10----11" format
     # the bits (as a range) against which "pattern" matches
     "bitsel",
     "suffix",     # shift the opcode down before decoding
     "subdecoders"  # list of further subdecoders for *additional* matches,
     # *ONLY* after "pattern" has *ALSO* been matched against.
     ])

power_op_types = {'function_unit': Function,
                  'internal_op': MicrOp,
                  'form': Form,
                  'asmcode': 8,
                  'in1_sel': In1Sel,
                  'in2_sel': In2Sel,
                  'in3_sel': In3Sel,
                  'out_sel': OutSel,
                  'cr_in': CRInSel,
                  'cr_out': CROutSel,
                  'ldst_len': LdstLen,
                  'upd': LDSTMode,
                  'rc_sel': RC,
                  'cry_in': CryIn
                  }

power_op_csvmap = {'function_unit': 'unit',
                   'form' : 'form',
                   'internal_op' : 'internal op',
                   'in1_sel' : 'in1',
                   'in2_sel' : 'in2',
                   'in3_sel' : 'in3',
                   'out_sel' : 'out',
                   'cr_in' : 'CR in',
                   'cr_out' : 'CR out',
                   'ldst_len' : 'ldst len',
                   'upd' : 'upd',
                   'rc_sel' : 'rc',
                   'cry_in' : 'cry in',
            }

def get_pname(field, pname):
    if pname is None:
        return field
    return "%s_%s" % (pname, field)


class PowerOp:
    """PowerOp: spec for execution.  op type (ADD etc.) reg specs etc.

    this is an internal data structure, set up by reading CSV files
    (which uses _eq to initialise each instance, not eq)

    the "public" API (as far as actual usage as a useful decoder is concerned)
    is Decode2ToExecute1Type

    the "subset" allows for only certain columns to be decoded
    """

    def __init__(self, incl_asm=True, name=None, subset=None):
        self.subset = subset
        debug_report = set()
        fields = set()
        for field, ptype in power_op_types.items():
            fields.add(field)
            if subset and field not in subset:
                continue
            fname = get_pname(field, name)
            setattr(self, field, Signal(ptype, reset_less=True, name=fname))
            debug_report.add(field)
        for bit in single_bit_flags:
            field = get_signal_name(bit)
            fields.add(field)
            if subset and field not in subset:
                continue
            debug_report.add(field)
            fname = get_pname(field, name)
            setattr(self, field, Signal(reset_less=True, name=fname))
        print ("PowerOp debug", name, debug_report)
        print ("        fields", fields)

    def _eq(self, row=None):
        if row is None:
            row = default_values
        # TODO: this conversion process from a dict to an object
        # should really be done using e.g. namedtuple and then
        # call eq not _eq
        if False:  # debugging
            if row['CR in'] == '1':
                import pdb
                pdb.set_trace()
                print(row)
            if row['CR out'] == '0':
                import pdb
                pdb.set_trace()
                print(row)
            print(row)
        ldst_mode = row['upd']
        if ldst_mode.isdigit():
            row['upd'] = int(ldst_mode)
        res = []
        for field, ptype in power_op_types.items():
            if not hasattr(self, field):
                continue
            if field not in power_op_csvmap:
                continue
            csvname = power_op_csvmap[field]
            val = row[csvname]
            if csvname == 'upd' and isinstance(val, int): # LDSTMode different
                val = ptype(val)
            else:
                val = ptype[val]
            res.append(getattr(self, field).eq(val))
        if False:
            print(row.keys())
        asmcode = row['comment']
        if hasattr(self, "asmcode") and asmcode in asmidx:
            res.append(self.asmcode.eq(asmidx[asmcode]))
        for bit in single_bit_flags:
            field = get_signal_name(bit)
            if not hasattr(self, field):
                continue
            sig = getattr(self, field)
            res.append(sig.eq(int(row.get(bit, 0))))
        return res

    def _get_eq(self, res, field, otherop):
        copyfrom = getattr(otherop, field, None)
        copyto = getattr(self, field, None)
        if copyfrom is not None and copyto is not None:
            res.append(copyto.eq(copyfrom))

    def eq(self, otherop):
        res = []
        for field in power_op_types.keys():
            self._get_eq(res, field, otherop)
        for bit in single_bit_flags:
            self._get_eq(res, get_signal_name(bit), otherop)
        return res

    def ports(self):
        res = []
        for field in power_op_types.keys():
            if hasattr(self, field):
                res.append(getattr(self, field))
        if hasattr(self, "asmcode"):
            res.append(self.asmcode)
        for field in single_bit_flags:
            field = get_signal_name(field)
            if hasattr(self, field):
                res.append(getattr(self, field))
        return res


class PowerDecoder(Elaboratable):
    """PowerDecoder - decodes an incoming opcode into the type of operation
    """

    def __init__(self, width, dec, name=None, col_subset=None, row_subset=None):
        self.pname = name
        self.col_subset = col_subset
        self.row_subsetfn = row_subset
        if not isinstance(dec, list):
            dec = [dec]
        self.dec = dec
        self.opcode_in = Signal(width, reset_less=True)

        self.op = PowerOp(name=name, subset=col_subset)
        for d in dec:
            if d.suffix is not None and d.suffix >= width:
                d.suffix = None
        self.width = width

    def suffix_mask(self, d):
        return ((1 << d.suffix) - 1)

    def divide_opcodes(self, d):
        divided = {}
        mask = self.suffix_mask(d)
        print("mask", hex(mask))
        for row in d.opcodes:
            opcode = row['opcode']
            if d.opint and '-' not in opcode:
                opcode = int(opcode, 0)
            key = opcode & mask
            opcode = opcode >> d.suffix
            if key not in divided:
                divided[key] = []
            r = row.copy()
            r['opcode'] = opcode
            divided[key].append(r)
        return divided

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # note: default opcode is "illegal" as this is a combinatorial block
        # this only works because OP_ILLEGAL=0 and the default (unset) is 0

        # go through the list of CSV decoders first
        for d in self.dec:
            opcode_switch = Signal(d.bitsel[1] - d.bitsel[0],
                                   reset_less=True)
            comb += opcode_switch.eq(self.opcode_in[d.bitsel[0]:d.bitsel[1]])
            if d.suffix:
                opcodes = self.divide_opcodes(d)
                opc_in = Signal(d.suffix, reset_less=True)
                comb += opc_in.eq(opcode_switch[:d.suffix])
                # begin the dynamic Switch statement here
                with m.Switch(opc_in):
                    for key, row in opcodes.items():
                        bitsel = (d.suffix+d.bitsel[0], d.bitsel[1])
                        sd = Subdecoder(pattern=None, opcodes=row,
                                        bitsel=bitsel, suffix=None,
                                        opint=False, subdecoders=[])
                        subdecoder = PowerDecoder(width=32, dec=sd,
                                                  name=self.pname,
                                                  col_subset=self.col_subset,
                                                  row_subset=self.row_subsetfn)
                        mname = get_pname("dec_sub%d" % key, self.pname)
                        setattr(m.submodules, mname, subdecoder)
                        comb += subdecoder.opcode_in.eq(self.opcode_in)
                        # XXX hmmm...
                        #if self.row_subsetfn:
                        #    if not self.row_subsetfn(key, row):
                        #        continue
                        # add in the dynamic Case statement here
                        with m.Case(key):
                            comb += self.op.eq(subdecoder.op)
            else:
                # TODO: arguments, here (all of them) need to be a list.
                # a for-loop around the *list* of decoder args.
                with m.Switch(opcode_switch):
                    self.handle_subdecoders(m, d)
                    for row in d.opcodes:
                        opcode = row['opcode']
                        if d.opint and '-' not in opcode:
                            opcode = int(opcode, 0)
                        if not row['unit']:
                            continue
                        if self.row_subsetfn:
                            if not self.row_subsetfn(opcode, row):
                                continue
                        # add in the dynamic Case statement here
                        with m.Case(opcode):
                            comb += self.op._eq(row)
        return m

    def handle_subdecoders(self, m, d):
        for dec in d.subdecoders:
            subdecoder = PowerDecoder(self.width, dec,
                                     name=self.pname,
                                     col_subset=self.col_subset,
                                     row_subset=self.row_subsetfn)
            if isinstance(dec, list):  # XXX HACK: take first pattern
                dec = dec[0]
            mname = get_pname("dec%d" % dec.pattern, self.pname)
            setattr(m.submodules, mname, subdecoder)
            m.d.comb += subdecoder.opcode_in.eq(self.opcode_in)
            with m.Case(dec.pattern):
                m.d.comb += self.op.eq(subdecoder.op)

    def ports(self):
        return [self.opcode_in] + self.op.ports()


class TopPowerDecoder(PowerDecoder):
    """TopPowerDecoder

    top-level hierarchical decoder for POWER ISA
    bigendian dynamically switches between big and little endian decoding
    (reverses byte order).  See V3.0B p44 1.11.2
    """

    def __init__(self, width, dec, name=None, col_subset=None, row_subset=None):
        PowerDecoder.__init__(self, width, dec, name, col_subset, row_subset)
        self.fields = df = DecodeFields(SignalBitRange, [self.opcode_in])
        self.fields.create_specs()
        self.raw_opcode_in = Signal.like(self.opcode_in, reset_less=True)
        self.bigendian = Signal(reset_less=True)

        for fname, value in self.fields.common_fields.items():
            signame = get_pname(fname, name)
            sig = Signal(value[0:-1].shape(), reset_less=True, name=signame)
            setattr(self, fname, sig)

        # create signals for all field forms
        self.form_names = forms = self.fields.instrs.keys()
        self.sigforms = {}
        for form in forms:
            fields = self.fields.instrs[form]
            fk = fields.keys()
            Fields = namedtuple("Fields", fk)
            sf = {}
            for k, value in fields.items():
                fname = "%s_%s" % (form, k)
                sig = Signal(value[0:-1].shape(), reset_less=True, name=fname)
                sf[k] = sig
            instr = Fields(**sf)
            setattr(self, "Form%s" % form, instr)
            self.sigforms[form] = instr

    def elaborate(self, platform):
        m = PowerDecoder.elaborate(self, platform)
        comb = m.d.comb
        # raw opcode in assumed to be in LE order: byte-reverse it to get BE
        raw_le = self.raw_opcode_in
        l = []
        for i in range(0, self.width, 8):
            l.append(raw_le[i:i+8])
        l.reverse()
        raw_be = Cat(*l)
        comb += self.opcode_in.eq(Mux(self.bigendian, raw_be, raw_le))

        # add all signal from commonly-used fields
        for fname, value in self.fields.common_fields.items():
            sig = getattr(self, fname)
            comb += sig.eq(value[0:-1])

        # link signals for all field forms
        forms = self.form_names
        for form in forms:
            sf = self.sigforms[form]
            fields = self.fields.instrs[form]
            for k, value in fields.items():
                sig = getattr(sf, k)
                comb += sig.eq(value[0:-1])

        return m

    def ports(self):
        return [self.raw_opcode_in, self.bigendian] + PowerDecoder.ports(self)


####################################################
# PRIMARY FUNCTION SPECIFYING THE FULL POWER DECODER

def create_pdecode(name=None, col_subset=None, row_subset=None):
    """create_pdecode - creates a cascading hierarchical POWER ISA decoder

    subsetting of the PowerOp decoding is possible by setting col_subset
    """

    # minor 19 has extra patterns
    m19 = []
    m19.append(Subdecoder(pattern=19, opcodes=get_csv("minor_19.csv"),
                          opint=True, bitsel=(1, 11), suffix=None,
                          subdecoders=[]))
    m19.append(Subdecoder(pattern=19, opcodes=get_csv("minor_19_00000.csv"),
                          opint=True, bitsel=(1, 6), suffix=None,
                          subdecoders=[]))

    # minor opcodes.
    pminor = [
        m19,
        Subdecoder(pattern=30, opcodes=get_csv("minor_30.csv"),
                   opint=True, bitsel=(1, 5), suffix=None, subdecoders=[]),
        Subdecoder(pattern=31, opcodes=get_csv("minor_31.csv"),
                   opint=True, bitsel=(1, 11), suffix=0b00101, subdecoders=[]),
        Subdecoder(pattern=58, opcodes=get_csv("minor_58.csv"),
                   opint=True, bitsel=(0, 2), suffix=None, subdecoders=[]),
        Subdecoder(pattern=62, opcodes=get_csv("minor_62.csv"),
                   opint=True, bitsel=(0, 2), suffix=None, subdecoders=[]),
    ]

    # top level: extra merged with major
    dec = []
    opcodes = get_csv("major.csv")
    dec.append(Subdecoder(pattern=None, opint=True, opcodes=opcodes,
                          bitsel=(26, 32), suffix=None, subdecoders=pminor))
    opcodes = get_csv("extra.csv")
    dec.append(Subdecoder(pattern=None, opint=False, opcodes=opcodes,
                          bitsel=(0, 32), suffix=None, subdecoders=[]))

    return TopPowerDecoder(32, dec, name=name, col_subset=col_subset,
                                               row_subset=row_subset)


if __name__ == '__main__':

    # row subset

    def rowsubsetfn(opcode, row):
        print ("row_subset", opcode, row)
        return row['unit'] == 'ALU'

    pdecode = create_pdecode(name="rowsub",
                             col_subset={'function_unit', 'in1_sel'},
                             row_subset=rowsubsetfn)
    vl = rtlil.convert(pdecode, ports=pdecode.ports())
    with open("row_subset_decoder.il", "w") as f:
        f.write(vl)

    # col subset

    pdecode = create_pdecode(name="fusubset", col_subset={'function_unit'})
    vl = rtlil.convert(pdecode, ports=pdecode.ports())
    with open("col_subset_decoder.il", "w") as f:
        f.write(vl)

    # full decoder

    pdecode = create_pdecode()
    vl = rtlil.convert(pdecode, ports=pdecode.ports())
    with open("decoder.il", "w") as f:
        f.write(vl)

