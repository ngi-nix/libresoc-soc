from soc.regfile.regfiles import FastRegs
from soc.decoder.power_enums import SPR

def fast_reg_to_spr(spr_num):
    if spr_num == FastRegs.CTR:
        return SPR.CTR.value
    elif spr_num == FastRegs.LR:
        return SPR.LR.value
    elif spr_num == FastRegs.TAR:
        return SPR.TAR.value
    elif spr_num == FastRegs.SRR0:
        return SPR.SRR0.value
    elif spr_num == FastRegs.SRR1:
        return SPR.SRR1.value


def spr_to_fast_reg(spr_num):
    if not isinstance(spr_num, str):
        spr_num = spr_dict[spr_num].SPR
    if spr_num == 'CTR':
        return FastRegs.CTR
    elif spr_num == 'LR':
        return FastRegs.LR
    elif spr_num == 'TAR':
        return FastRegs.TAR
    elif spr_num == 'SRR0':
        return FastRegs.SRR0
    elif spr_num == 'SRR1':
        return FastRegs.SRR1
