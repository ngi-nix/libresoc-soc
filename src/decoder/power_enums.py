from enum import Enum, unique


@unique
class Function(Enum):
    ALU = 0
    LDST = 1


@unique
class InternalOp(Enum):
    OP_ADD = 0
    OP_AND = 1
    OP_B = 2
    OP_BC = 3
    OP_CMP = 4
    OP_LOAD = 5
    OP_MUL_L64 = 6
    OP_OR = 7
    OP_RLC = 8
    OP_STORE = 9
    OP_TDI = 10
    OP_XOR = 11


@unique
class In1Sel(Enum):
    RA = 0
    RA_OR_ZERO = 1
    NONE = 2
    SPR = 3


@unique
class In2Sel(Enum):
    CONST_SI = 0
    CONST_SI_HI = 1
    CONST_UI = 2
    CONST_UI_HI = 3
    CONST_LI = 4
    CONST_BD = 5
    CONST_SH32 = 6
    RB = 7


@unique
class In3Sel(Enum):
    NONE = 0
    RS = 1


@unique
class OutSel(Enum):
    RT = 0
    RA = 1
    NONE = 2
    SPR = 3


@unique
class LdstLen(Enum):
    NONE = 0
    is1B = 1
    is2B = 2
    is4B = 3


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
