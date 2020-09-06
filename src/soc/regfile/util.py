from soc.regfile.regfiles import FastRegs
from soc.decoder.power_enums import SPR, spr_dict

spr_to_fast = { SPR.CTR: FastRegs.CTR,
                SPR.LR: FastRegs.LR,
                SPR.TAR: FastRegs.TAR,
                SPR.SRR0: FastRegs.SRR0,
                SPR.SRR1: FastRegs.SRR1,
                SPR.XER: FastRegs.XER,
                SPR.DEC: FastRegs.DEC,
                SPR.TB: FastRegs.TB,
               }

sprstr_to_fast = {}
fast_to_spr = {}
for (k, v) in spr_to_fast.items():
    sprstr_to_fast[k.name] = v
    fast_to_spr[v] = k

def fast_reg_to_spr(spr_num):
    return fast_to_spr[spr_num].value


def spr_to_fast_reg(spr_num):
    if not isinstance(spr_num, str):
        spr_num = spr_dict[spr_num].SPR
    return sprstr_to_fast[spr_num]


def slow_reg_to_spr(slow_reg):
    for i, x in enumerate(SPR):
        if slow_reg == i:
            return x.value


def spr_to_slow_reg(spr_num):
    for i, x in enumerate(SPR):
        if spr_num == x.value:
            return i
