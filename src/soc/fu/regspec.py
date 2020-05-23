# see https://libre-soc.org/3d_gpu/architecture/regfile/ section on regspecs

def get_regspec_bitwidth(regspec, srcdest, idx):
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

    def get_out(self, i):
        if isinstance(self.rwid, int): # old - testing - API (rwid is int)
            return self.alu.out[i]
        # regspec-based API: look up variable through regspec according to row number
        return getattr(self.alu.n.data_o, self.rwid[1][i][1])

    def get_in(self, i):
        if isinstance(self.rwid, int): # old - testing - API (rwid is int)
            return self.alu.i[i]
        # regspec-based API: look up variable through regspec according to row number
        return getattr(self.alu.p.data_i, self.rwid[0][i][1])

    def get_op(self):
        if isinstance(self.rwid, int): # old - testing - API (rwid is int)
            return self.alu.op
        return self.alu.p.data_i.ctx.op
