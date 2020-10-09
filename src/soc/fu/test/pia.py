import power_instruction_analyzer as pia


def pia_res_to_output(pia_res):
    assert isinstance(pia_res, pia.InstructionOutput)
    retval = {}
    if pia_res.rt is not None:
        retval["o"] = pia_res.rt
    if pia_res.cr0 is not None:
        cr0 = pia_res.cr0
        v = 0
        if cr0.lt:
            v |= 8
        if cr0.gt:
            v |= 4
        if cr0.eq:
            v |= 2
        if cr0.so:
            v |= 1
        retval["cr_a"] = v
    if pia_res.overflow is not None:
        overflow = pia_res.overflow
        v = 0
        if overflow.ov:
            v |= 1
        if overflow.ov32:
            v |= 2
        retval["xer_ov"] = v
        retval["xer_so"] = overflow.so
    else:
        retval["xer_ov"] = 0
        retval["xer_so"] = 0
    if pia_res.carry is not None:
        carry = pia_res.carry
        v = 0
        if carry.ca:
            v |= 1
        if carry.ca32:
            v |= 2
        retval["xer_ca"] = v
    else:
        retval["xer_ca"] = 0
    return retval
