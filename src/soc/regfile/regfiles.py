# POWER9 Register Files
"""POWER9 regfiles

Defines the following register files:

    * INT regfile   - 32x 64-bit
    * SPR regfile   - 110x 64-bit
    * CR regfile    - CR0-7
    * XER regfile   - XER.so, XER.ca/ca32, XER.ov/ov32
    * FAST regfile  - PC, MSR, CTR, LR, TAR, SRR1, SRR2

Links:

* https://bugs.libre-soc.org/show_bug.cgi?id=345
* https://bugs.libre-soc.org/show_bug.cgi?id=351
* https://libre-soc.org/3d_gpu/architecture/regfile/
* https://libre-soc.org/openpower/isatables/sprs.csv
"""

# TODO

from soc.regfile.regfile import RegFile, RegFileArray
from soc.regfile.virtual_port import VirtualRegPort
from soc.decoder.power_enums import SPR


# Integer Regfile
class IntRegs(RegFileArray):
    """IntRegs

    * QTY 32of 64-bit registers
    * 3R2W
    * Array-based unary-indexed (not binary-indexed)
    * write-through capability (read on same cycle as write)
    """
    def __init__(self):
        super().__init__(64, 32)
        self.w_ports = [self.write_port("dest1"),
                        self.write_port("dest2")] # for now (LD/ST update)
        self.r_ports = [self.read_port("src1"),
                        self.read_port("src2"),
                        self.read_port("src3")]


# Fast SPRs Regfile
class FastRegs(RegFileArray):
    """FastRegs

    FAST regfile  - PC, MSR, CTR, LR, TAR, SRR1, SRR2

    * QTY 8of 64-bit registers
    * 3R2W
    * Array-based unary-indexed (not binary-indexed)
    * write-through capability (read on same cycle as write)
    """
    PC = 0
    MSR = 1
    CTR = 2
    LR = 3
    TAR = 4
    SRR1 = 5
    SRR2 = 6
    def __init__(self):
        super().__init__(64, 8)
        self.w_ports = [self.write_port("dest1"),
                        self.write_port("dest2")]
        self.r_ports = [self.read_port("src1"),
                        self.read_port("src2"),
                        self.read_port("src3")]


# CR Regfile
class CRRegs(VirtualRegPort):
    """Condition Code Registers (CR0-7)

    * QTY 8of 8-bit registers
    * 3R1W 4-bit-wide with additional 1R1W for the "full" 32-bit width
    * Array-based unary-indexed (not binary-indexed)
    * write-through capability (read on same cycle as write)
    """
    def __init__(self):
        super().__init__(32, 8)
        self.w_ports = [self.full_wr, # 32-bit wide (masked, 8-en lines)
                        self.write_port("dest")] # 4-bit wide, unary-indexed
        self.r_ports = [self.full_rd, # 32-bit wide (masked, 8-en lines)
                        self.read_port("src1"),
                        self.read_port("src2"),
                        self.read_port("src3")]


# XER Regfile
class XERRegs(VirtualRegPort):
    """XER Registers (SO, CA/CA32, OV/OV32)

    * QTY 3of 2-bit registers
    * 3R3W 2-bit-wide with additional 1R1W for the "full" 6-bit width
    * Array-based unary-indexed (not binary-indexed)
    * write-through capability (read on same cycle as write)
    """
    SO=0 # this is actually 2-bit but we ignore 1 bit of it
    CA=1 # CA and CA32
    OV=2 # OV and OV32
    def __init__(self):
        super().__init__(6, 2)
        self.w_ports = [self.full_wr, # 6-bit wide (masked, 3-en lines)
                        self.write_port("dest1"),
                        self.write_port("dest2"),
                        self.write_port("dest3")]
        self.r_ports = [self.full_rd, # 6-bit wide (masked, 3-en lines)
                        self.read_port("src1"),
                        self.read_port("src2"),
                        self.read_port("src3")]


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
        self.r_ports = [self.read_port("src")]

# class containing all regfiles: int, cr, xer, fast, spr
class RegFiles:
    def __init__(self):
        self.rf = {}
        for (name, kls) in [('int', IntRegs),
                            ('cr', CRRegs),
                            ('xer', XERRegs),
                            ('fasr', FastRegs),
                            ('spr', SPRRegs),]:
            rf = self.rf[name] = kls()
            setattr(self, name, rf)

    def elaborate_into(self, m, platform):
        for (name, rf) in self.rf.items():
            setattr(m.submodules, name, rf)
        return m

