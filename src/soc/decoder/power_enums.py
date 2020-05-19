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
single_bit_flags = ['CR in', 'CR out', 'inv A', 'inv out',
                    'cry out', 'BR', 'sgn ext', 'upd', 'rsrv', '32b',
                    'sgn', 'lk', 'sgl pipe']

# default values for fields in the table
default_values = {'unit': "NONE", 'internal op': "OP_ILLEGAL",
                  'in1': "RA", 'in2': 'NONE', 'in3': 'NONE', 'out': 'NONE',
                  'ldst len': 'NONE',
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
    ALU = 1
    LDST = 2
    SHIFT_ROT = 3
    LOGICAL = 4
    BRANCH = 5
    CR = 6
    TRAP = 7


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


# Internal Operation numbering.  Add new opcodes here (FPADD, FPMUL etc.)
@unique
class InternalOp(Enum):
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


@unique
class In1Sel(Enum):
    NONE = 0
    RA = 1
    RA_OR_ZERO = 2
    SPR = 3


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


@unique
class In3Sel(Enum):
    NONE = 0
    RS = 1


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
    is4B = 3
    is8B = 4


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


# SPRs - Special-Purpose Registers.  See V3.0B Figure 18 p971 and
# http://libre-riscv.org/openpower/isatables/sprs.csv
# http://bugs.libre-riscv.org/show_bug.cgi?id=261

spr_csv = get_csv("sprs.csv")
spr_info = namedtuple('spr_info', 'SPR priv_mtspr priv_mfspr length')
spr_dict = {}
for row in spr_csv:
    info = spr_info(SPR=row['SPR'], priv_mtspr=row['priv_mtspr'],
                    priv_mfspr=row['priv_mfspr'], length=int(row['len']))
    spr_dict[int(row['Idx'])] = info
fields = [(row['SPR'], int(row['Idx'])) for row in spr_csv]
SPR = Enum('SPR', fields)


XER_bits = {
    'SO': 32,
    'OV': 33,
    'CA': 34,
    'OV32': 44,
    'CA32': 45
    }
