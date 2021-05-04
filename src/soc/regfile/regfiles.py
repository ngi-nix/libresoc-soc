# POWER9 Register Files
"""POWER9 regfiles

Defines the following register files:

    * INT regfile   - 32x 64-bit
    * SPR regfile   - 110x 64-bit
    * CR regfile    - CR0-7
    * XER regfile   - XER.so, XER.ca/ca32, XER.ov/ov32
    * FAST regfile  - CTR, LR, TAR, SRR1, SRR2
    * STATE regfile  - PC, MSR, (SimpleV VL later)

Note: this should NOT have name conventions hard-coded (dedicated ports per
regname).  However it is convenient for now.

Links:

* https://bugs.libre-soc.org/show_bug.cgi?id=345
* https://bugs.libre-soc.org/show_bug.cgi?id=351
* https://libre-soc.org/3d_gpu/architecture/regfile/
* https://libre-soc.org/openpower/isatables/sprs.csv
* https://libre-soc.org/openpower/sv/sprs/ (SVSTATE)
"""

# TODO

from soc.regfile.regfile import RegFile, RegFileArray, RegFileMem
from soc.regfile.virtual_port import VirtualRegPort
from openpower.decoder.power_enums import SPRfull, SPRreduced

# XXX MAKE DAMN SURE TO KEEP THESE UP-TO-DATE if changing/adding regs
from openpower.consts import StateRegsEnum, XERRegsEnum, FastRegsEnum


# "State" Regfile
class StateRegs(RegFileArray, StateRegsEnum):
    """StateRegs

    State regfile  - PC, MSR, SVSTATE (for SimpleV)

    * QTY 3of 64-bit registers
    * 4R3W
    * Array-based unary-indexed (not binary-indexed)
    * write-through capability (read on same cycle as write)

    Note: d_wr1 d_rd1 are for use by the decoder, to get at the PC.
    will probably have to also add one so it can get at the MSR as well.
    (d_rd2)

    """
    def __init__(self, svp64_en=False, regreduce_en=False):
        super().__init__(64, StateRegsEnum.N_REGS)
        self.w_ports = {'nia': self.write_port("nia"),
                        'msr': self.write_port("msr"),
                        'svstate': self.write_port("svstate"),
                        'sv': self.write_port("sv"), # writing SVSTATE (issuer)
                        'd_wr1': self.write_port("d_wr1")} # writing PC (issuer)
        self.r_ports = {'cia': self.read_port("cia"), # reading PC (issuer)
                        'msr': self.read_port("msr"), # reading MSR (issuer)
                        'sv': self.read_port("sv"), # reading SV (issuer)
                        }


# Integer Regfile
class IntRegs(RegFileMem): #class IntRegs(RegFileArray):
    """IntRegs

    * QTY 32of 64-bit registers
    * 3R2W
    * Array-based unary-indexed (not binary-indexed)
    * write-through capability (read on same cycle as write)
    """
    def __init__(self, svp64_en=False, regreduce_en=False):
        super().__init__(64, 32, fwd_bus_mode=not regreduce_en)
        self.w_ports = {'o': self.write_port("dest1"),
                        }
        self.r_ports = {
                        'dmi': self.read_port("dmi")} # needed for Debug (DMI)
        if svp64_en:
            self.r_ports['pred'] = self.read_port("pred") # for predicate mask
        if not regreduce_en:
            self.w_ports['o1'] = self.write_port("dest2") # (LD/ST update)
            self.r_ports['ra'] = self.read_port("src1")
            self.r_ports['rb'] = self.read_port("src2")
            self.r_ports['rc'] = self.read_port("src3")
        else:
            self.r_ports['rabc'] = self.read_port("src1")


# Fast SPRs Regfile
class FastRegs(RegFileMem, FastRegsEnum): #RegFileArray):
    """FastRegs

    FAST regfile  - CTR, LR, TAR, SRR1, SRR2, XER, TB, DEC, SVSRR0

    * QTY 6of 64-bit registers
    * 3R2W
    * Array-based unary-indexed (not binary-indexed)
    * write-through capability (read on same cycle as write)

    Note: r/w issue are used by issuer to increment/decrement TB/DEC.
    """
    def __init__(self, svp64_en=False, regreduce_en=False):
        super().__init__(64, FastRegsEnum.N_REGS, fwd_bus_mode=not regreduce_en)
        self.w_ports = {'fast1': self.write_port("dest1"),
                        'issue': self.write_port("issue"), # writing DEC/TB
                       }
        self.r_ports = {'fast1': self.read_port("src1"),
                        'issue': self.read_port("issue"), # reading DEC/TB
                        }
        if not regreduce_en:
            self.r_ports['fast2'] = self.read_port("src2")


# CR Regfile
class CRRegs(VirtualRegPort):
    """Condition Code Registers (CR0-7)

    * QTY 8of 8-bit registers
    * 3R1W 4-bit-wide with additional 1R1W for the "full" 32-bit width
    * Array-based unary-indexed (not binary-indexed)
    * write-through capability (read on same cycle as write)
    """
    def __init__(self, svp64_en=False, regreduce_en=False):
        super().__init__(32, 8, rd2=True)
        self.w_ports = {'full_cr': self.full_wr, # 32-bit (masked, 8-en lines)
                        'cr_a': self.write_port("dest1"), # 4-bit, unary-indexed
                        'cr_b': self.write_port("dest2")} # 4-bit, unary-indexed
        self.r_ports = {'full_cr': self.full_rd, # 32-bit (masked, 8-en lines)
                        'full_cr_dbg': self.full_rd2, # for DMI
                        'cr_a': self.read_port("src1"),
                        'cr_b': self.read_port("src2"),
                        'cr_c': self.read_port("src3")}
        if svp64_en:
            self.r_ports['cr_pred'] = self.read_port("cr_pred") # for predicate


# XER Regfile
class XERRegs(VirtualRegPort, XERRegsEnum):
    """XER Registers (SO, CA/CA32, OV/OV32)

    * QTY 3of 2-bit registers
    * 3R3W 2-bit-wide with additional 1R1W for the "full" 6-bit width
    * Array-based unary-indexed (not binary-indexed)
    * write-through capability (read on same cycle as write)
    """
    SO=0 # this is actually 2-bit but we ignore 1 bit of it
    CA=1 # CA and CA32
    OV=2 # OV and OV32
    def __init__(self, svp64_en=False, regreduce_en=False):
        super().__init__(6, XERRegsEnum.N_REGS)
        self.w_ports = {'full_xer': self.full_wr, # 6-bit (masked, 3-en lines)
                        'xer_so': self.write_port("dest1"),
                        'xer_ca': self.write_port("dest2"),
                        'xer_ov': self.write_port("dest3")}
        self.r_ports = {'full_xer': self.full_rd, # 6-bit (masked, 3-en lines)
                        'xer_so': self.read_port("src1"),
                        'xer_ca': self.read_port("src2"),
                        'xer_ov': self.read_port("src3")}


# SPR Regfile
class SPRRegs(RegFileMem):
    """SPRRegs

    * QTY len(SPRs) 64-bit registers
    * 1R1W
    * binary-indexed but REQUIRES MAPPING
    * write-through capability (read on same cycle as write)
    """
    def __init__(self, svp64_en=False, regreduce_en=False):
        if regreduce_en:
            n_sprs = len(SPRreduced)
        else:
            n_sprs = len(SPRfull)
        super().__init__(width=64, depth=n_sprs,
                         fwd_bus_mode=not regreduce_en)
        self.w_ports = {'spr1': self.write_port("spr1")}
        self.r_ports = {'spr1': self.read_port("spr1")}


# class containing all regfiles: int, cr, xer, fast, spr
class RegFiles:
    def __init__(self, pspec):
        # test is SVP64 is to be enabled
        svp64_en = hasattr(pspec, "svp64") and (pspec.svp64 == True)

        # and regfile port reduction
        regreduce_en = hasattr(pspec, "regreduce") and \
                      (pspec.regreduce == True)

        self.rf = {}
        # create regfiles here, Factory style
        for (name, kls) in [('int', IntRegs),
                            ('cr', CRRegs),
                            ('xer', XERRegs),
                            ('fast', FastRegs),
                            ('state', StateRegs),
                            ('spr', SPRRegs),]:
            rf = self.rf[name] = kls(svp64_en, regreduce_en)
            # also add these as instances, self.state, self.fast, self.cr etc.
            setattr(self, name, rf)

    def elaborate_into(self, m, platform):
        for (name, rf) in self.rf.items():
            setattr(m.submodules, name, rf)
        return m

