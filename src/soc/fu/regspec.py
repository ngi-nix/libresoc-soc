"""RegSpecs

see https://libre-soc.org/3d_gpu/architecture/regfile/ section on regspecs

this module is a key strategic module that links pipeline specifications
(soc.fu.*.pipe_data and soc.fo.*.pipeline) to MultiCompUnits.  MultiCompUnits
know absolutely nothing about the data passing through them: all they know
is: how many inputs they need to manage, and how many outputs.

regspecs tell MultiCompUnit what the ordering of the inputs is, how many to
create, and how to connect them up to the ALU being "managed" by this CompUnit.
likewise for outputs.

later (TODO) the Register Files will be connected to MultiCompUnits, and,
again, the regspecs will say which Regfile (which type) is connected to
which MultiCompUnit port, how wide the connection is, and so on.

"""
from nmigen import Const
from soc.regfile.regfiles import XERRegs, FastRegs

def get_regspec_bitwidth(regspec, srcdest, idx):
    print ("get_regspec_bitwidth", regspec, srcdest, idx)
    bitspec = regspec[srcdest][idx]
    wid = 0
    print (bitspec)
    for ranges in bitspec[2].split(","):
        ranges = ranges.split(":")
        print (ranges)
        if len(ranges) == 1: # only one bit
            wid += 1
        else:
            start, end = map(int, ranges)
            wid += (end-start)+1
    return wid


class RegSpec:
    def __init__(self, rwid, n_src=None, n_dst=None, name=None):
        self._rwid = rwid
        if isinstance(rwid, int):
            # rwid: integer (covers all registers)
            self._n_src, self._n_dst = n_src, n_dst
        else:
            # rwid: a regspec.
            self._n_src, self._n_dst = len(rwid[0]), len(rwid[1])

    def _get_dstwid(self, i):
        if isinstance(self._rwid, int):
            return self._rwid
        return get_regspec_bitwidth(self._rwid, 1, i)

    def _get_srcwid(self, i):
        if isinstance(self._rwid, int):
            return self._rwid
        return get_regspec_bitwidth(self._rwid, 0, i)


class RegSpecALUAPI:
    def __init__(self, rwid, alu):
        """RegSpecAPI

        * :rwid:       regspec
        * :alu:        ALU covered by this regspec
        """
        self.rwid = rwid
        self.alu = alu # actual ALU - set as a "submodule" of the CU

    def get_in_name(self, i):
        return self.rwid[0][i][1]

    def get_out_name(self, i):
        return self.rwid[1][i][1]

    def get_out(self, i):
        if isinstance(self.rwid, int): # old - testing - API (rwid is int)
            return self.alu.out[i]
        # regspec-based API: look up variable through regspec thru row number
        return getattr(self.alu.n.data_o, self.get_out_name(i))

    def get_in(self, i):
        if isinstance(self.rwid, int): # old - testing - API (rwid is int)
            return self.alu.i[i]
        # regspec-based API: look up variable through regspec thru row number
        return getattr(self.alu.p.data_i, self.get_in_name(i))

    def get_op(self):
        if isinstance(self.rwid, int): # old - testing - API (rwid is int)
            return self.alu.op
        return self.alu.p.data_i.ctx.op


# function for the relationship between regspecs and Decode2Execute1Type
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
            return e.oe.oe & e.oe.oe_ok, SO, SO
        if name == 'xer_ov':
            return e.oe.oe & e.oe.oe_ok, OV, OV
        if name == 'xer_ca':
            return e.input_carry, CA, CA

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
            return Const(1), PC, PC
        if name == 'msr':
            return Const(1), MSR, MSR
        # TODO: remap the SPR numbers to FAST regs
        if name == 'spr1':
            return e.read_spr1.ok, 1<<e.read_spr1.data, 1<<e.write_spr.data
        if name == 'spr2':
            return e.read_spr2.ok, 1<<e.read_spr2.data, 1<<e.write_spr.data

    assert False, "regspec not found %s %d" % (repr(regspec), idx)
