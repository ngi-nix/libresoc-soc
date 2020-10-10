"""DMI "simulator" process for nmigen tests
"""

from soc.debug.dmi import  DBGCore, DBGCtrl, DBGStat

def dmi_sim(dut):

    ctrl_reg = 0b100 # terminated

    dmi = dut.dmi
    while not dut.stop:
        # wait for req
        req = yield dmi.req_i
        if req == 0:
            yield
            continue

        # check read/write and address
        wen = yield dmi.we_i
        addr = yield dmi.addr_i
        print ("        dmi wen, addr", wen, addr)

        # Control read
        if addr == DBGCore.CTRL and wen == 0:
            print ("        read ctrl reg", ctrl_reg)
            yield dmi.dout.eq(ctrl_reg)
            yield dmi.ack_o.eq(1)
            yield
            yield dmi.ack_o.eq(0)

        # Control write
        elif addr == DBGCore.CTRL and wen == 1:
            stat = (yield dmi.din)
            if (stat & (1<<DBGCtrl.STOP)):
                ctrl_reg |= (1<<DBGStat.STOPPED)
                ctrl_reg &= ~(1<<DBGStat.STOPPING)
            if (stat & (1<<DBGCtrl.START)):
                ctrl_reg = 0
            print ("        write ctrl reg", stat, ctrl_reg)
            yield dmi.ack_o.eq(1)
            yield
            yield dmi.ack_o.eq(0)

        # allow MSR write
        elif addr == DBGCore.MSR and wen == 0:
            print ("        read msr reg")
            yield dmi.dout.eq(0xdeadbeef) # test MSR value
            yield dmi.ack_o.eq(1)
            yield
            yield dmi.ack_o.eq(0)
        else:
            # do nothing but just ack it
            yield dmi.ack_o.eq(1)
            yield
            yield dmi.ack_o.eq(0)

    print ("dmi sim stopping")
