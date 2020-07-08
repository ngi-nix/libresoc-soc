# Listed in V3.0B Book III Chap 4.2.1
# MSR bit numbers

class MSR:
    SF  = (63 - 0)     # Sixty-Four bit mode
    HV  = (63 - 3)     # Hypervisor state
    S   = (63 - 41)    # Secure state
    EE  = (63 - 48)    # External interrupt Enable
    PR  = (63 - 49)    # PRoblem state
    FP  = (63 - 50)    # FP available
    ME  = (63 - 51)    # Machine Check int enable
    IR  = (63 - 58)    # Instruction Relocation
    DR  = (63 - 59)    # Data Relocation
    PMM = (63 - 60)    # Performance Monitor Mark
    RI  = (63 - 62)    # Recoverable Interrupt
    LE  = (63 - 63)    # Little Endian

# Listed in V3.0B Book III 7.5.9 "Program Interrupt"

# note that these correspond to trap_input_record.traptype bits 0,1,2,3
# (TODO: add more?)

class PI:
    FP    = (63 - 43)    # 1 if FP exception
    ILLEG = (63 - 44)    # 1 if illegal instruction (not doing hypervisor)
    PRIV  = (63 - 45)    # 1 if privileged interrupt
    TRAP  = (63 - 46)    # 1 if exception is "trap" type
    ADR   = (63 - 47)    # 0 if SRR0 = address of instruction causing exception

