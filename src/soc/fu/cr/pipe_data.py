"""
Links:
* https://libre-soc.org/3d_gpu/architecture/regfile/ section on regspecs
"""
from soc.fu.pipe_data import FUBaseData, CommonPipeSpec
from soc.fu.cr.cr_input_record import CompCROpSubset


class CRInputData(FUBaseData):
    regspec = [('INT', 'ra', '0:63'),      # 64 bit range
               ('INT', 'rb', '0:63'),      # 64 bit range
               ('CR', 'full_cr', '0:31'), # 32 bit range
               ('CR', 'cr_a', '0:3'),     # 4 bit range
               ('CR', 'cr_b', '0:3'),     # 4 bit range
               ('CR', 'cr_c', '0:3')]     # 4 bit: for CR_OP partial update
    def __init__(self, pspec):
        super().__init__(pspec, False)
        # convenience
        self.a, self.b = self.ra, self.rb


class CROutputData(FUBaseData):
    regspec = [('INT', 'o', '0:63'),      # RA - 64 bit range
               ('CR', 'full_cr', '0:31'), # 32 bit range
               ('CR', 'cr_a', '0:3')]     # 4 bit range
    def __init__(self, pspec):
        super().__init__(pspec, True)
        # convenience
        self.cr = self.cr_a


class CRPipeSpec(CommonPipeSpec):
    regspec = (CRInputData.regspec, CROutputData.regspec)
    opsubsetkls = CompCROpSubset
