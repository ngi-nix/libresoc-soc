# Listed in V3.0B Book III Chap 4.2.1
# MSR bit numbers

class MSR:
    SF  = (63 - 0)     # Sixty-Four bit mode
    HV  = (63 - 3)     # Hypervisor state
    UND = (63 - 5)     # Undefined behavior state (see Bk 2, Sect. 3.2.1)
    TSs = (63 - 29)    # Transactional State (subfield)
    TSe = (63 - 30)    # Transactional State (subfield)
    TM  = (63 - 31)    # Transactional Memory Available
    VEC = (63 - 38)    # Vector Available
    VSX = (63 - 40)    # VSX Available
    S   = (63 - 41)    # Secure state
    EE  = (63 - 48)    # External interrupt Enable
    PR  = (63 - 49)    # PRoblem state
    FP  = (63 - 50)    # FP available
    ME  = (63 - 51)    # Machine Check int enable
    FE0 = (63 - 52)    # Floating-Point Exception Mode 0
    TEs = (63 - 53)    # Trace Enable (subfield)
    TEe = (63 - 54)    # Trace Enable (subfield)
    FE1 = (63 - 55)    # Floating-Point Exception Mode 1
    IR  = (63 - 58)    # Instruction Relocation
    DR  = (63 - 59)    # Data Relocation
    PMM = (63 - 60)    # Performance Monitor Mark
    RI  = (63 - 62)    # Recoverable Interrupt
    LE  = (63 - 63)    # Little Endian

# Listed in V3.0B Book III 7.5.9 "Program Interrupt"

# note that these correspond to trap_input_record.traptype bits 0,1,2,3,4
# (TODO: add more?)
# IMPORTANT: when adding extra bits here it is CRITICALLY IMPORTANT
# to expand traptype to cope with the increased range

class PI:
    TM_BAD_THING = (63 - 42) # 1 for a TM Bad Thing type interrupt
    FP    = (63 - 43)    # 1 if FP exception
    ILLEG = (63 - 44)    # 1 if illegal instruction (not doing hypervisor)
    PRIV  = (63 - 45)    # 1 if privileged interrupt
    TRAP  = (63 - 46)    # 1 if exception is "trap" type
    ADR   = (63 - 47)    # 0 if SRR0 = address of instruction causing exception

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
