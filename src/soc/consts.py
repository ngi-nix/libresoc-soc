# sigh create little-ended versions of bitfield flags
def botchify(bekls, lekls):
    for attr in dir(bekls):
        if attr[0] == '_':
            continue
        setattr(lekls, attr, 63-getattr(bekls, attr))

# Listed in V3.0B Book III Chap 4.2.1
# MSR bit numbers, *bigendian* order (PowerISA format)
# use this in the simulator
class MSRb:
    SF  = 0     # Sixty-Four bit mode
    HV  = 3     # Hypervisor state
    UND = 5     # Undefined behavior state (see Bk 2, Sect. 3.2.1)
    TSs = 29    # Transactional State (subfield)
    TSe = 30    # Transactional State (subfield)
    TM  = 31    # Transactional Memory Available
    VEC = 38    # Vector Available
    VSX = 40    # VSX Available
    S   = 41    # Secure state
    EE  = 48    # External interrupt Enable
    PR  = 49    # PRoblem state
    FP  = 50    # FP available
    ME  = 51    # Machine Check int enable
    FE0 = 52    # Floating-Point Exception Mode 0
    TEs = 53    # Trace Enable (subfield)
    TEe = 54    # Trace Enable (subfield)
    FE1 = 55    # Floating-Point Exception Mode 1
    IR  = 58    # Instruction Relocation
    DR  = 59    # Data Relocation
    PMM = 60    # Performance Monitor Mark
    RI  = 62    # Recoverable Interrupt
    LE  = 63    # Little Endian

# use this inside the HDL (where everything is little-endian)
class MSR:
    pass

botchify(MSRb, MSR)

# Listed in V3.0B Book III 7.5.9 "Program Interrupt"

# note that these correspond to trap_input_record.traptype bits 0,1,2,3,4
# (TODO: add more?)
# IMPORTANT: when adding extra bits here it is CRITICALLY IMPORTANT
# to expand traptype to cope with the increased range

# use this in the simulator
class PIb:
    TM_BAD_THING = 42 # 1 for a TM Bad Thing type interrupt
    FP           = 43    # 1 if FP exception
    ILLEG        = 44    # 1 if illegal instruction (not doing hypervisor)
    PRIV         = 45    # 1 if privileged interrupt
    TRAP         = 46    # 1 if exception is "trap" type
    ADR          = 47    # 0 if SRR0 = address of instruction causing exception

# and use this in the HDL
class PI:
    pass

botchify(PIb, PI)

# see traptype (and trap main_stage.py)
# IMPORTANT: when adding extra bits here it is CRITICALLY IMPORTANT
# to expand traptype to cope with the increased range

class TT:
    FP = 1<<0
    PRIV = 1<<1
    TRAP = 1<<2
    ADDR = 1<<3
    ILLEG = 1<<4 # currently the max, therefore traptype must be 5 bits
    # TODO: support for TM_BAD_THING (not included yet in trap main_stage.py)
    size = 5 # MUST update this to contain the full number of Trap Types
