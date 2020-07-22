from enum import Enum, unique
import csv
import os
from os.path import dirname, join
from collections import namedtuple


def find_wiki_file(name):
    filedir = os.path.dirname(os.path.abspath(__file__))
    basedir = dirname(dirname(dirname(filedir)))
    tabledir = join(basedir, 'libreriscv')
    tabledir = join(tabledir, 'openpower')
    tabledir = join(tabledir, 'isatables')

    file_path = join(tabledir, name)
    return file_path


def get_csv(name):
    file_path = find_wiki_file(name)
    with open(file_path, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        return list(reader)


# names of the fields in the tables that don't correspond to an enum
single_bit_flags = ['inv A', 'inv out',
                    'cry out', 'BR', 'sgn ext', 'rsrv', '32b',
                    'sgn', 'lk', 'sgl pipe']

# default values for fields in the table
default_values = {'unit': "NONE", 'internal op': "OP_ILLEGAL",
                  'in1': "RA", 'in2': 'NONE', 'in3': 'NONE', 'out': 'NONE',
                  'CR in': 'NONE',
                  'ldst len': 'NONE',
                  'upd': '0',
                  'rc': 'NONE', 'cry in': 'ZERO', 'form': 'NONE'}


def get_signal_name(name):
    if name[0].isdigit():
        name = "is_" + name
    return name.lower().replace(' ', '_')

# this corresponds to which Function Unit (pipeline-with-Reservation-Stations)
# is to process and guard the operation.  they are roughly divided by having
# the same register input/output signature (X-Form, etc.)
@unique
class Function(Enum):
    NONE = 0
    ALU = 1 << 1
    LDST = 1 << 2
    SHIFT_ROT = 1 << 3
    LOGICAL = 1 << 4
    BRANCH = 1 << 5
    CR = 1 << 6
    TRAP = 1 << 7
    MUL = 1 << 8
    DIV = 1 << 9
    SPR = 1 << 10


@unique
class Form(Enum):
    NONE = 0
    I = 1
    B = 2
    SC = 3
    D = 4
    DS = 5
    DQ = 6
    DX = 7
    X = 8
    XL = 9
    XFX = 10
    XFL = 11
    XX1 = 12
    XX2 = 13
    XX3 = 14
    XX4 = 15
    XS = 16
    XO = 17
    A = 18
    M = 19
    MD = 20
    MDS = 21
    VA = 22
    VC = 23
    VX = 24
    EVX = 25
    EVS = 26
    Z22 = 27
    Z23 = 28


# supported instructions: make sure to keep up-to-date with CSV files
# just like everything else
_insns = [
    "NONE", "add", "addc", "addco", "adde", "addeo", "addi", "addic", "addic.",
    "addis", "addme", "addmeo", "addo", "addze", "addzeo", "and", "andc",
    "andi.", "andis.", "attn", "b", "bc", "bcctr", "bclr", "bctar",
    "bpermd", "cmp", "cmpb", "cmpeqb", "cmpi", "cmpl", "cmpli", "cmprb",
    "cntlzd", "cntlzw", "cnttzd", "cnttzw", "crand", "crandc", "creqv",
    "crnand", "crnor", "cror", "crorc", "crxor", "darn", "dcbf", "dcbst",
    "dcbt", "dcbtst", "dcbz", "divd", "divde", "divdeo", "divdeu",
    "divdeuo", "divdo", "divdu", "divduo", "divw", "divwe", "divweo",
    "divweu", "divweuo", "divwo", "divwu", "divwuo", "eqv", "extsb",
    "extsh", "extsw", "extswsli", "icbi", "icbt", "isel", "isync",
    "lbarx", "lbz", "lbzu", "lbzux", "lbzx", "ld", "ldarx", "ldbrx",
    "ldu", "ldux", "ldx", "lha", "lharx", "lhau", "lhaux", "lhax",
    "lhbrx", "lhz", "lhzu", "lhzux", "lhzx", "lwa", "lwarx", "lwaux",
    "lwax", "lwbrx", "lwz", "lwzu", "lwzux", "lwzx", "mcrf", "mcrxr",
    "mcrxrx", "mfcr/mfocrf", "mfmsr", "mfspr", "modsd", "modsw", "modud",
    "moduw", "mtcrf/mtocrf", "mtmsr", "mtmsrd", "mtspr", "mulhd", "mulhdu",
    "mulhw", "mulhwu", "mulld", "mulldo", "mulli", "mullw", "mullwo",
    "nand", "neg", "nego", "nop", "nor", "or", "orc", "ori", "oris",
    "popcntb", "popcntd", "popcntw", "prtyd", "prtyw", "rfid", "rldcl",
    "rldcr", "rldic", "rldicl", "rldicr", "rldimi", "rlwimi", "rlwinm",
    "rlwnm", "setb", "sim_cfg", "sld", "slw", "srad", "sradi", "sraw",
    "srawi", "srd", "srw", "stb", "stbcx", "stbu", "stbux", "stbx", "std",
    "stdbrx", "stdcx", "stdu", "stdux", "stdx", "sth", "sthbrx", "sthcx",
    "sthu", "sthux", "sthx", "stw", "stwbrx", "stwcx", "stwu", "stwux",
    "stwx", "subf", "subfc", "subfco", "subfe", "subfeo", "subfic",
    "subfme", "subfmeo", "subfo", "subfze", "subfzeo", "sync", "td",
    "tdi", "tw", "twi", "xor", "xori", "xoris",
]

# two-way lookup of instruction-to-index and vice-versa
insns = {}
asmidx = {}
for i, insn in enumerate(_insns):
    insns[i] = insn
    asmidx[insn] = i

# Internal Operation numbering.  Add new opcodes here (FPADD, FPMUL etc.)
@unique
class MicrOp(Enum):
    OP_ILLEGAL = 0     # important that this is zero (see power_decoder.py)
    OP_NOP = 1
    OP_ADD = 2
    OP_ADDPCIS = 3
    OP_AND = 4
    OP_ATTN = 5
    OP_B = 6
    OP_BC = 7
    OP_BCREG = 8
    OP_BPERM = 9
    OP_CMP = 10
    OP_CMPB = 11
    OP_CMPEQB = 12
    OP_CMPRB = 13
    OP_CNTZ = 14
    OP_CRAND = 15
    OP_CRANDC = 16
    OP_CREQV = 17
    OP_CRNAND = 18
    OP_CRNOR = 19
    OP_CROR = 20
    OP_CRORC = 21
    OP_CRXOR = 22
    OP_DARN = 23
    OP_DCBF = 24
    OP_DCBST = 25
    OP_DCBT = 26
    OP_DCBTST = 27
    OP_DCBZ = 28
    OP_DIV = 29
    OP_DIVE = 30
    OP_EXTS = 31
    OP_EXTSWSLI = 32
    OP_ICBI = 33
    OP_ICBT = 34
    OP_ISEL = 35
    OP_ISYNC = 36
    OP_LOAD = 37
    OP_STORE = 38
    OP_MADDHD = 39
    OP_MADDHDU = 40
    OP_MADDLD = 41
    OP_MCRF = 42
    OP_MCRXR = 43
    OP_MCRXRX = 44
    OP_MFCR = 45
    OP_MFSPR = 46
    OP_MOD = 47
    OP_MTCRF = 48
    OP_MTSPR = 49
    OP_MUL_L64 = 50
    OP_MUL_H64 = 51
    OP_MUL_H32 = 52
    OP_OR = 53
    OP_POPCNT = 54
    OP_PRTY = 55
    OP_RLC = 56
    OP_RLCL = 57
    OP_RLCR = 58
    OP_SETB = 59
    OP_SHL = 60
    OP_SHR = 61
    OP_SYNC = 62
    OP_TRAP = 63
    OP_XOR = 67
    OP_SIM_CONFIG = 68
    OP_CROP = 69
    OP_RFID = 70
    OP_MFMSR = 71
    OP_MTMSRD = 72
    OP_SC = 73
    OP_MTMSR = 74


@unique
class In1Sel(Enum):
    NONE = 0
    RA = 1
    RA_OR_ZERO = 2
    SPR = 3
    RS = 4  # for some ALU/Logical operations


@unique
class In2Sel(Enum):
    NONE = 0
    RB = 1
    CONST_UI = 2
    CONST_SI = 3
    CONST_UI_HI = 4
    CONST_SI_HI = 5
    CONST_LI = 6
    CONST_BD = 7
    CONST_DS = 8
    CONST_M1 = 9
    CONST_SH = 10
    CONST_SH32 = 11
    SPR = 12
    RS = 13  # for shiftrot (M-Form)


@unique
class In3Sel(Enum):
    NONE = 0
    RS = 1
    RB = 2  # for shiftrot (M-Form)


@unique
class OutSel(Enum):
    NONE = 0
    RT = 1
    RA = 2
    SPR = 3


@unique
class LdstLen(Enum):
    NONE = 0
    is1B = 1
    is2B = 2
    is4B = 4
    is8B = 8


@unique
class LDSTMode(Enum):
    NONE = 0
    update = 1
    cix = 2
    cx = 3


@unique
class RC(Enum):
    NONE = 0
    ONE = 1
    RC = 2


@unique
class CryIn(Enum):
    ZERO = 0
    ONE = 1
    CA = 2


@unique
class CRInSel(Enum):
    NONE = 0
    CR0 = 1
    BI = 2
    BFA = 3
    BA_BB = 4
    BC = 5
    WHOLE_REG = 6


@unique
class CROutSel(Enum):
    NONE = 0
    CR0 = 1
    BF = 2
    BT = 3
    WHOLE_REG = 4


# SPRs - Special-Purpose Registers.  See V3.0B Figure 18 p971 and
# http://libre-riscv.org/openpower/isatables/sprs.csv
# http://bugs.libre-riscv.org/show_bug.cgi?id=261

spr_csv = get_csv("sprs.csv")
spr_info = namedtuple('spr_info', 'SPR priv_mtspr priv_mfspr length idx')
spr_dict = {}
spr_byname = {}
for row in spr_csv:
    info = spr_info(SPR=row['SPR'], priv_mtspr=row['priv_mtspr'],
                    priv_mfspr=row['priv_mfspr'], length=int(row['len']),
                    idx=int(row['Idx']))
    spr_dict[int(row['Idx'])] = info
    spr_byname[row['SPR']] = info
fields = [(row['SPR'], int(row['Idx'])) for row in spr_csv]
SPR = Enum('SPR', fields)


XER_bits = {
    'SO': 32,
    'OV': 33,
    'CA': 34,
    'OV32': 44,
    'CA32': 45
}

if __name__ == '__main__':
    # find out what the heck is in SPR enum :)
    print("sprs", len(SPR))
    print(dir(SPR))
    print(dir(Enum))
    print(SPR.__members__['TAR'])
    for x in SPR:
        print(x, x.value, str(x), x.name)
