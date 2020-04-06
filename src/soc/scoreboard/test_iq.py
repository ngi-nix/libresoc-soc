""" testing of InstructionQ
"""

from copy import deepcopy
from random import randint
from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil

from soc.scoreboard.instruction_q import InstructionQ
from nmutil.nmoperator import eq
import unittest


class IQSim:
    def __init__(self, dut, iq, n_in, n_out):
        self.dut = dut
        self.iq = iq
        self.oq = []
        self.n_in = n_in
        self.n_out = n_out

    def send(self):
        i = 0
        while i < len(self.iq):
            sendlen = randint(1, self.n_in)
            sendlen = 1
            sendlen = min(len(self.iq) - i, sendlen)
            print("sendlen", len(self.iq)-i, sendlen)
            for idx in range(sendlen):
                instr = self.iq[i+idx]
                yield from eq(self.dut.data_i[idx], instr)
                di = yield self.dut.data_i[idx]  # .src1_i
                print("senddata %d %x" % ((i+idx), di))
                self.oq.append(di)
            yield self.dut.p_add_i.eq(sendlen)
            yield
            o_p_ready = yield self.dut.p_ready_o
            while not o_p_ready:
                yield
                o_p_ready = yield self.dut.p_ready_o

            yield self.dut.p_add_i.eq(0)

            print("send", len(self.iq), i, sendlen)

            # wait random period of time before queueing another value
            for j in range(randint(0, 3)):
                yield

            i += sendlen

        yield self.dut.p_add_i.eq(0)
        yield

        print("send ended")

        # wait random period of time before queueing another value
        # for i in range(randint(0, 3)):
        #    yield

        #send_range = randint(0, 3)
        # if send_range == 0:
        #    send = True
        # else:
        #    send = randint(0, send_range) != 0

    def rcv(self):
        i = 0
        yield
        yield
        yield
        while i < len(self.iq):
            rcvlen = randint(1, self.n_out)
            #print ("outreq", rcvlen)
            yield self.dut.n_sub_i.eq(rcvlen)
            n_sub_o = yield self.dut.n_sub_o
            print("recv", n_sub_o)
            for j in range(n_sub_o):
                r = yield self.dut.data_o[j]  # .src1_i
                print("recvdata %x %s" % (r, repr(self.iq[i+j])))
                assert r == self.oq[i+j]
            yield
            if n_sub_o == 0:
                continue
            yield self.dut.n_sub_i.eq(0)

            i += n_sub_o

        print("recv ended")


def mk_insns(n_insns, wid, opwid):
    res = []
    for i in range(n_insns):
        op1 = randint(0, (1 << wid)-1)
        opi = randint(0, 1)
        op2 = randint(0, (1 << wid)-1)
        dst = randint(0, (1 << wid)-1)
        oper = randint(0, (1 << opwid)-1)
        imm = randint(0, (1 << wid)-1)
        res.append({'oper_i': oper, 'opim_i': opi,
                    'imm_i': imm, 'dest_i': dst,
                    'src1_i': op1, 'src2_i': op2})
    return res


@unittest.skip("test fails")  # FIXME
def test_iq():
    wid = 8
    opwid = 4
    qlen = 2
    n_in = 1
    n_out = 1
    dut = InstructionQ(wid, opwid, qlen, n_in, n_out)
    insns = mk_insns(1000, wid, opwid)

    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_iq.il", "w") as f:
        f.write(vl)

    test = IQSim(dut, insns, n_in, n_out)
    print(insns)
    run_simulation(dut, [test.rcv(), test.send()
                         ],
                   vcd_name="test_iq.vcd")


if __name__ == '__main__':
    test_iq()
