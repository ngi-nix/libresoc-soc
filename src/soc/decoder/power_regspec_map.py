"""regspec_decode

function for the relationship between regspecs and Decode2Execute1Type

see https://libre-soc.org/3d_gpu/architecture/regfile/ section on regspecs
"""
from nmigen import Const
from soc.regfile.regfiles import XERRegs, FastRegs
from soc.decoder.power_enums import CryIn


def regspec_decode(e, regfile, name):
    """regspec_decode

    this function encodes the understanding (relationship) between
    Regfiles, Computation Units, and the Power ISA Decoder (PowerDecoder2).

    based on the regspec, which contains the register file name and register
    name, return a tuple of:

    * how the decoder should determine whether the Function Unit needs
      a Regport or not
    * which Regfile port should be read to get that data
    * when it comes to writing: likewise, which Regfile port should be written

    Note that some of the port numbering encoding is *unary*.  in the case
    of "Full Condition Register", it's a full 8-bit mask of read/write-enables.
    This actually matches directly with the XFX field in MTCR, and at
    some point that 8-bit mask from the instruction could actually be passed        directly through to full_cr (TODO).

    For the INT and CR numbering, these are expressed in binary in the
    instruction (note however that XFX in MTCR is unary-masked!)

    XER is implicitly-encoded based on whether the operation has carry or
    overflow.

    FAST regfile is, again, implicitly encoded, back in PowerDecode2, based
    on the type of operation (see DecodeB for an example).

    The SPR regfile on the other hand is *binary*-encoded, and, furthermore,
    has to be "remapped".
    """

    if regfile == 'INT':
        # Int register numbering is *unary* encoded
        if name == 'ra': # RA
            return e.read_reg1.ok, 1<<e.read_reg1.data, None
        if name == 'rb': # RB
            return e.read_reg2.ok, 1<<e.read_reg2.data, None
        if name == 'rc': # RS
            return e.read_reg3.ok, 1<<e.read_reg3.data, None
        if name == 'o': # RT
            return e.write_reg.ok, None, 1<<e.write_reg.data
        if name == 'o1': # RA (update mode: LD/ST EA)
            return e.write_ea.ok, None, 1<<e.write_ea.data

    if regfile == 'CR':
        # CRRegs register numbering is *unary* encoded
        if name == 'full_cr': # full CR
            return e.read_cr_whole, 0b11111111, 0b11111111
        if name == 'cr_a': # CR A
            return e.read_cr1.ok, 1<<e.read_cr1.data, 1<<e.write_cr.data
        if name == 'cr_b': # CR B
            return e.read_cr2.ok, 1<<e.read_cr2.data, None
        if name == 'cr_c': # CR C
            return e.read_cr3.ok, 1<<e.read_cr2.data, None

    if regfile == 'XER':
        # XERRegs register numbering is *unary* encoded
        SO = 1<<XERRegs.SO
        CA = 1<<XERRegs.CA
        OV = 1<<XERRegs.OV
        if name == 'xer_so':
            return e.oe.oe[0] & e.oe.oe_ok, SO, SO
        if name == 'xer_ov':
            return e.oe.oe[0] & e.oe.oe_ok, OV, OV
        if name == 'xer_ca':
            return (e.input_carry == CryIn.CA.value), CA, CA

    if regfile == 'FAST':
        # FAST register numbering is *unary* encoded
        PC = 1<<FastRegs.PC
        MSR = 1<<FastRegs.MSR
        CTR = 1<<FastRegs.CTR
        LR = 1<<FastRegs.LR
        TAR = 1<<FastRegs.TAR
        SRR1 = 1<<FastRegs.SRR1
        SRR2 = 1<<FastRegs.SRR2
        if name in ['cia', 'nia']:
            return Const(1), PC, PC # TODO: detect read-conditions
        if name == 'msr':
            return Const(1), MSR, MS # TODO: detect read-conditions
        # TODO: remap the SPR numbers to FAST regs
        if name == 'spr1':
            return e.read_fast1.ok, 1<<e.read_fast1.data, 1<<e.write_fast1.data
        if name == 'spr2':
            return e.read_fast2.ok, 1<<e.read_fast2.data, 1<<e.write_fast2.data

    if regfile == 'SPR':
        assert False, "regfile TODO %s %s %d" % (refgile, repr(regspec), idx)
    assert False, "regspec not found %s %s %d" % (refgile, repr(regspec), idx)
