# POWER9 Register Files
"""POWER9 regfiles

Defines the following register files:

    * INT regfile
    * SPR regfile
    * CR regfile
    * XER regfile
    * FAST regfile

Links:

* https://bugs.libre-soc.org/show_bug.cgi?id=345
* https://libre-soc.org/3d_gpu/architecture/regfile/
* https://libre-soc.org/openpower/isatables/sprs.csv
"""

# TODO

from soc.regfile import RegFile, RegFileArray
from soc.decoder.power_enums import SPR


# Integer Regfile
class IntRegs(RegFileArray):
    """IntRegs

    * QTY 32of 64-bit registers
    * 3R1W
    * Array-based unary-indexed (not binary-indexed)
    * write-through capability (read on same cycle as write)
    """
    def __init__(self):
        super().__init__(64, 32)
        self.w_ports = [self.write_port("dest")]
        self.r_ports = [self.write_port("src1"),
                        self.write_port("src2"),
                        self.write_port("src3")]


# CR Regfile
class CRRegs(RegFileArray):
    """Condition Code Registers (CR0-7)

    * QTY 8of 8-bit registers
    * 8R8W (!) with additional 1R1W for the "full" width
    * Array-based unary-indexed (not binary-indexed)
    * write-through capability (read on same cycle as write)
    """
    def __init__(self):
        super().__init__(4, 8)
        self.w_ports = [self.write_port("dest")]
        self.r_ports = [self.write_port("src1"),
                        self.write_port("src2"),
                        self.write_port("src3")]


# SPR Regfile
class SPRRegs(RegFile):
    """SPRRegs

    * QTY len(SPRs) 64-bit registers
    * 1R1W
    * binary-indexed but REQUIRES MAPPING
    * write-through capability (read on same cycle as write)
    """
    def __init__(self):
        n_sprs = len(SPR)
        super().__init__(64, n_sprs)
        self.w_ports = [self.write_port("dest")]
        self.r_ports = [self.write_port("src")]
