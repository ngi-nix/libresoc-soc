# sigh create little-ended versions of bitfield flags
def botchify(bekls, lekls):
    for attr in dir(bekls):
        if attr[0] == '_':
            continue
        setattr(lekls, attr, 63-getattr(bekls, attr))


# Can't think of a better place to put these functions.
# Return an arbitrary subfield of a larger field.
def field_slice(msb0_start, msb0_end, field_width=64):
    """field_slice

    Answers with a subfield slice of the signal r ("register"),
    where the start and end bits use IBM "MSB 0" conventions.

    see: https://en.wikipedia.org/wiki/Bit_numbering#MSB_0_bit_numbering

    * assertion: msb0_start < msb0_end.
    * The range specified is inclusive on both ends.
    * field_width specifies the total number of bits (note: not bits-1)
    """
    if msb0_start >= msb0_end:
        raise ValueError(
            "start ({}) must be less than end ({})".format(msb0_start, msb0_end)
        )
    # sigh.  MSB0 (IBM numbering) is inverted.  converting to python
    # we *swap names* so as not to get confused by having "end, start"
    lsb0_end = (field_width-1) - msb0_start
    lsb0_start = (field_width-1) - msb0_end

    return slice(lsb0_start, lsb0_end + 1)


def field(r, msb0_start, msb0_end=None, field_width=64):
    """Answers with a subfield of the signal r ("register"), where
    the start and end bits use IBM conventions.  start < end, if
    end is provided.  The range specified is inclusive on both ends.

    Answers with a subfield of the signal r ("register"),
    where the start and end bits use IBM "MSB 0" conventions.
    If end is not provided, a single bit subfield is returned.

    see: https://en.wikipedia.org/wiki/Bit_numbering#MSB_0_bit_numbering

    * assertion: msb0_start < msb0_end.
    * The range specified is inclusive on both ends.
    * field_width specifies the total number of bits (note: not bits-1)

    Example usage:

        comb += field(insn, 0, 6, field_width=32).eq(17)
        # NOTE: NEVER DIRECTLY ACCESS OPCODE FIELDS IN INSTRUCTIONS.
        # This example is purely for illustrative purposes only.
        # Use self.fields.FormXYZ.etcetc instead.

        comb += field(msr, MSRb.TEs, MSRb.TEe).eq(0)

    Proof by substitution:

           field(insn, 0, 6, field_width=32).eq(17)
        == insn[field_slice(0, 6, field_width=32)].eq(17)
        == insn[slice((31-6), (31-0)+1)].eq(17)
        == insn[slice(25, 32)].eq(17)
        == insn[25:32].eq(17)

           field(msr, MSRb.TEs, MSRb.TEe).eq(0)
        == field(msr, 53, 54).eq(0)
        == msr[field_slice(53, 54)].eq(0)
        == msr[slice((63-54), (63-53)+1)].eq(0)  # note cross-over!
        == msr[slice(9, 11)].eq(0)
        == msr[9:11].eq(0)
    """
    if msb0_end is None:
        return r[(field_width - 1) - msb0_start]
    else:
        return r[field_slice(msb0_start, msb0_end)]


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
    TM_BAD_THING = 42    # 1 for a TM Bad Thing type interrupt
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
    EINT = 1<<4  # external interrupt
    DEC = 1<<5   # decrement counter
    MEMEXC = 1<<6 # LD/ST exception
    ILLEG = 1<<7 # currently the max
    # TODO: support for TM_BAD_THING (not included yet in trap main_stage.py)
    size = 8 # MUST update this to contain the full number of Trap Types
