from soc.regfile.regfiles import FastRegs
from soc.decoder.power_enums import SPR

def fast_reg_to_spr(spr_num):
    if spr_num == FastRegs.CTR:
        return SPR.CTR.value
    elif spr_num == FastRegs.LR:
        return SPR.LR.value
    elif spr_num == FastRegs.TAR:
        return SPR.TAR.value
