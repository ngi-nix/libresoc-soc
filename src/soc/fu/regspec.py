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
def regspec_rdmask(e, regspec, idx):
    (regfile, name, _) = regspec[idx]
    if regfile == 'INT':
        if name == 'ra': # RA
            return e.read_reg1.ok
        if name == 'rb': # RB
            return e.read_reg2.ok
        if name == 'rc': # RS
            return e.read_reg3.ok
    if regfile == 'CR':
        if name == 'full_cr': # full CR
            return e.read_cr_whole
        if name == 'cr_a': # CR A
            return e.read_cr1.ok
        if name == 'cr_b': # CR B
            return e.read_cr2.ok
        if name == 'cr_c': # CR C
            return e.read_cr3.ok
    if regfile == 'XER':
        if name in ['xer_so', 'xer_ov']:
            return e.oe.oe & e.oe.oe_ok
        if name == 'xer_ca':
            return e.input_carry

    assert False, "regspec rdmask not found %s %d" % (repr(regspec), idx)
