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
