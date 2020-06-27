from nmigen import Signal, Module, Record
from nmigen.back.pysim import Simulator, Delay
from nmigen.compat.sim import run_simulation, Settle
from nmutil.formaltest import FHDLTestCase
from nmigen.cli import rtlil
import unittest
from soc.config.test.test_loadstore import TestMemPspec
from soc.config.loadstore import ConfigMemoryPortInterface


def wait_busy(port, no=False):
    while True:
        busy = yield port.pi.busy_o
        print("busy", no, busy)
        if bool(busy) == no:
            break
        yield


def wait_addr(port):
    while True:
        addr_ok = yield port.pi.addr_ok_o
        print("addrok", addr_ok)
        if addr_ok:
            break
        yield


def wait_ldok(port):
    while True:
        ldok = yield port.pi.ld.ok
        print("ldok", ldok)
        if ldok:
            break
        yield


def l0_cache_st(dut, addr, data, datalen):
    if isinstance(dut.pi, Record):
        port1 = dut
    else:
        port1 = dut.pi

    # have to wait until not busy
    yield from wait_busy(port1, no=False)    # wait until not busy

    # set up a ST on the port.  address first:
    yield port1.pi.is_st_i.eq(1)  # indicate ST
    yield port1.pi.data_len.eq(datalen)  # ST length (1/2/4/8)

    yield port1.pi.addr.data.eq(addr)  # set address
    yield port1.pi.addr.ok.eq(1)  # set ok
    yield Settle()
    yield from wait_addr(port1)             # wait until addr ok
    # yield # not needed, just for checking
    # yield # not needed, just for checking
    # assert "ST" for one cycle (required by the API)
    yield port1.pi.st.data.eq(data)
    yield port1.pi.st.ok.eq(1)
    yield
    yield port1.pi.st.ok.eq(0)

    # can go straight to reset.
    yield port1.pi.is_st_i.eq(0)  # end
    yield port1.pi.addr.ok.eq(0)  # set !ok
    # yield from wait_busy(port1, False)    # wait until not busy


def l0_cache_ld(dut, addr, datalen):

    if isinstance(dut.pi, Record):
        port1 = dut
    else:
        port1 = dut.pi

    # have to wait until not busy
    yield from wait_busy(port1, no=False)    # wait until not busy

    # set up a LD on the port.  address first:
    yield port1.pi.is_ld_i.eq(1)  # indicate LD
    yield port1.pi.data_len.eq(datalen)  # LD length (1/2/4/8)

    yield port1.pi.addr.data.eq(addr)  # set address
    yield port1.pi.addr.ok.eq(1)  # set ok
    yield Settle()
    yield from wait_addr(port1)             # wait until addr ok
    yield
    yield from wait_ldok(port1)             # wait until ld ok
    data = yield port1.pi.ld.data

    # cleanup
    yield port1.pi.is_ld_i.eq(0)  # end
    yield port1.pi.addr.ok.eq(0)  # set !ok
    # yield from wait_busy(port1, no=False)    # wait until not busy

    return data


def l0_cache_ldst(arg, dut):

    # do two half-word stores at consecutive addresses, then two loads
    addr1 = 0x04
    addr2 = addr1 + 0x2
    data = 0xbeef
    data2 = 0xf00f
    #data = 0x4
    yield from l0_cache_st(dut, addr1, data, 2)
    yield from l0_cache_st(dut, addr2, data2, 2)
    result = yield from l0_cache_ld(dut, addr1, 2)
    result2 = yield from l0_cache_ld(dut, addr2, 2)
    arg.assertEqual(data, result, "data %x != %x" % (result, data))
    arg.assertEqual(data2, result2, "data2 %x != %x" % (result2, data2))

    # now load both in a 32-bit load to make sure they're really consecutive
    data3 = data | (data2 << 16)
    result3 = yield from l0_cache_ld(dut, addr1, 4)
    arg.assertEqual(data3, result3, "data3 %x != %x" % (result3, data3))


def tst_config_pi(testcls, ifacetype):
    """set up a configureable memory test of type ifacetype
    """
    dut = Module()
    pspec = TestMemPspec(ldst_ifacetype=ifacetype,
                         addr_wid=48,
                         mask_wid=8,
                         reg_wid=64)
    cmpi = ConfigMemoryPortInterface(pspec)
    dut.submodules.pi = cmpi.pi
    if hasattr(cmpi, 'lsmem'): # hmmm not happy about this
        dut.submodules.lsmem = cmpi.lsmem.lsi
    vl = rtlil.convert(dut, ports=[])#dut.ports())
    with open("test_pi_%s.il" % ifacetype, "w") as f:
        f.write(vl)

    run_simulation(dut, {"sync": l0_cache_ldst(testcls, cmpi.pi)},
                   vcd_name='test_pi_%s.vcd' % ifacetype)


class TestPIMem(unittest.TestCase):

    def test_pi_mem(self):
        tst_config_pi(self, 'testpi')

    def test_pi2ls(self):
        tst_config_pi(self, 'testmem')


if __name__ == '__main__':
    unittest.main(exit=False)

