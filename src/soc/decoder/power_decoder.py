"""Cascading Power ISA Decoder

This module uses CSV tables in a hierarchical/peer cascading fashion,
to create a multi-level instruction decoder by recognising appropriate
patterns.  The output is a flattened (1-level) series of fields suitable
for a simple RISC engine.

This is based on Anton Blanchard's excellent microwatt work:
https://github.com/antonblanchard/microwatt/blob/master/decode1.vhdl

The basic principle is that the python code does the heavy lifting
(reading the CSV files, constructing the hierarchy), creating the HDL
AST with for-loops generating switch-case statements.

PowerDecoder takes a *list* of CSV files with an associated bit-range
that it is requested to match against the "opcode" row of the CSV file.
This pattern can be either an integer, a binary number, *or* a wildcard
nmigen Case pattern of the form "001--1-100".

Subdecoders are *additional* cases with further decoding.  The "pattern"
argument is specified as one of the Case statements (a peer of the opcode
row in the CSV file), and thus further fields of the opcode may be decoded
giving increasing levels of detail.

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

from nmigen import Module, Elaboratable, Signal, Cat, Mux
from nmigen.cli import rtlil
from soc.decoder.power_enums import (Function, Form, InternalOp,
                         In1Sel, In2Sel, In3Sel, OutSel, RC, LdstLen,
                         CryIn, get_csv, single_bit_flags,
                         get_signal_name, default_values)
from collections import namedtuple
from soc.decoder.power_fields import DecodeFields
from soc.decoder.power_fieldsn import SigDecode, SignalBitRange


Subdecoder = namedtuple("Subdecoder", ["pattern", "opcodes", "opint",
                                       "bitsel", "suffix", "subdecoders"])


class PowerOp:
    """PowerOp: spec for execution.  op type (ADD etc.) reg specs etc.
    """

    def __init__(self):
        self.function_unit = Signal(Function, reset_less=True)
        self.internal_op = Signal(InternalOp, reset_less=True)
        self.form = Signal(Form, reset_less=True)
        self.in1_sel = Signal(In1Sel, reset_less=True)
        self.in2_sel = Signal(In2Sel, reset_less=True)
        self.in3_sel = Signal(In3Sel, reset_less=True)
        self.out_sel = Signal(OutSel, reset_less=True)
        self.ldst_len = Signal(LdstLen, reset_less=True)
        self.rc_sel = Signal(RC, reset_less=True)
        self.cry_in = Signal(CryIn, reset_less=True)
        for bit in single_bit_flags:
            name = get_signal_name(bit)
            setattr(self, name, Signal(reset_less=True, name=name))

    def _eq(self, row=None):
        if row is None:
            row = default_values
        res = [self.function_unit.eq(Function[row['unit']]),
               self.form.eq(Form[row['form']]),
               self.internal_op.eq(InternalOp[row['internal op']]),
               self.in1_sel.eq(In1Sel[row['in1']]),
               self.in2_sel.eq(In2Sel[row['in2']]),
               self.in3_sel.eq(In3Sel[row['in3']]),
               self.out_sel.eq(OutSel[row['out']]),
               self.ldst_len.eq(LdstLen[row['ldst len']]),
               self.rc_sel.eq(RC[row['rc']]),
               self.cry_in.eq(CryIn[row['cry in']]),
               ]
        for bit in single_bit_flags:
            sig = getattr(self, get_signal_name(bit))
            res.append(sig.eq(int(row.get(bit, 0))))
        return res

    def eq(self, otherop):
        res = [self.function_unit.eq(otherop.function_unit),
               self.form.eq(otherop.form),
               self.internal_op.eq(otherop.internal_op),
               self.in1_sel.eq(otherop.in1_sel),
               self.in2_sel.eq(otherop.in2_sel),
               self.in3_sel.eq(otherop.in3_sel),
               self.out_sel.eq(otherop.out_sel),
               self.rc_sel.eq(otherop.rc_sel),
               self.ldst_len.eq(otherop.ldst_len),
               self.cry_in.eq(otherop.cry_in)]
        for bit in single_bit_flags:
            sig = getattr(self, get_signal_name(bit))
            res.append(sig.eq(getattr(otherop, get_signal_name(bit))))
        return res

    def ports(self):
        regular = [self.function_unit,
                   self.in1_sel,
                   self.in2_sel,
                   self.in3_sel,
                   self.out_sel,
                   self.ldst_len,
                   self.rc_sel,
                   self.internal_op,
                   self.form]
        single_bit_ports = [getattr(self, get_signal_name(x))
                            for x in single_bit_flags]
        return regular + single_bit_ports


class PowerDecoder(Elaboratable):
    """PowerDecoder - decodes an incoming opcode into the type of operation
    """

    def __init__(self, width, dec):
        if not isinstance(dec, list):
            dec = [dec]
        self.dec = dec
        self.opcode_in = Signal(width, reset_less=True)

        self.op = PowerOp()
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
                with m.Switch(opc_in):
                    for key, row in opcodes.items():
                        bitsel = (d.suffix+d.bitsel[0], d.bitsel[1])
                        sd = Subdecoder(pattern=None, opcodes=row,
                                        bitsel=bitsel, suffix=None,
                                        opint=False, subdecoders=[])
                        subdecoder = PowerDecoder(width=32, dec=sd)
                        setattr(m.submodules, "dec_sub%d" % key, subdecoder)
                        comb += subdecoder.opcode_in.eq(self.opcode_in)
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
                        with m.Case(opcode):
                            comb += self.op._eq(row)
        return m

    def handle_subdecoders(self, m, d):
        for dec in d.subdecoders:
            subdecoder = PowerDecoder(self.width, dec)
            if isinstance(dec, list): # XXX HACK: take first pattern
                dec = dec[0]
            setattr(m.submodules, "dec%d" % dec.pattern, subdecoder)
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

    def __init__(self, width, dec):
        PowerDecoder.__init__(self, width, dec)
        self.fields = DecodeFields(SignalBitRange, [self.opcode_in])
        self.fields.create_specs()
        self.raw_opcode_in = Signal.like(self.opcode_in, reset_less=True)
        self.bigendian = Signal(reset_less=True)

        for name in self.fields.common_fields:
            value = getattr(self.fields, name)
            sig = Signal(value[0:-1].shape(), reset_less=True, name=name)
            setattr(self, name, sig)

    def elaborate(self, platform):
        m = PowerDecoder.elaborate(self, platform)
        comb = m.d.comb
        raw_be = self.raw_opcode_in
        l = []
        for i in range(0, self.width, 8):
            l.append(raw_be[i:i+8])
        l.reverse()
        raw_le = Cat(*l)
        comb += self.opcode_in.eq(Mux(self.bigendian, raw_be, raw_le))
        for name in self.fields.common_fields:
            value = getattr(self.fields, name)
            sig = getattr(self, name)
            comb += sig.eq(value[0:-1])
        return m

    def ports(self):
        return [self.raw_opcode_in, self.bigendian] + PowerDecoder.ports(self)


def create_pdecode():

    # minor 19 has extra patterns
    m19 = []
    m19.append(Subdecoder(pattern=19, opcodes=get_csv("minor_19.csv"),
                   opint=True, bitsel=(1, 11), suffix=None, subdecoders=[]))
    m19.append(Subdecoder(pattern=19, opcodes=get_csv("minor_19_00000.csv"),
                   opint=True, bitsel=(1, 6), suffix=None, subdecoders=[]))

    # minor opcodes.
    pminor = [
        m19,
        Subdecoder(pattern=30, opcodes=get_csv("minor_30.csv"),
                   opint=True, bitsel=(1, 6), suffix=None, subdecoders=[]),
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

    return TopPowerDecoder(32, dec)


if __name__ == '__main__':
    pdecode = create_pdecode()
    vl = rtlil.convert(pdecode, ports=pdecode.ports())
    with open("decoder.il", "w") as f:
        f.write(vl)
