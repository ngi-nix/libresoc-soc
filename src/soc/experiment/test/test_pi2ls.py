from nmigen import Signal, Module, Record
from nmigen.back.pysim import Simulator, Delay
from nmigen.compat.sim import run_simulation, Settle
from nmutil.formaltest import FHDLTestCase
from nmigen.cli import rtlil
import unittest
from soc.experiment.pi2ls import Pi2LSUI
from soc.experiment.lsmem import TestMemLoadStoreUnit
from soc.experiment.pimem import TestMemoryPortInterface

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
        if not addr_ok:
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


def l0_cache_ld(dut, addr, datalen, expected):

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
    yield from wait_addr(port1)             # wait until addr ok

    yield from wait_ldok(port1)             # wait until ld ok
    data = yield port1.pi.ld.data

    # cleanup
    yield port1.pi.is_ld_i.eq(0)  # end
    yield port1.pi.addr.ok.eq(0)  # set !ok
    # yield from wait_busy(port1, no=False)    # wait until not busy

    return data


def l0_cache_ldst(arg, dut):
    yield
    addr = 0x2
    data = 0xbeef
    data2 = 0xf00f
    #data = 0x4
    yield from l0_cache_st(dut, 0x2, data, 2)
    yield from l0_cache_st(dut, 0x4, data2, 2)
    result = yield from l0_cache_ld(dut, 0x2, 2, data)
    result2 = yield from l0_cache_ld(dut, 0x4, 2, data2)
    yield
    arg.assertEqual(data, result, "data %x != %x" % (result, data))
    arg.assertEqual(data2, result2, "data2 %x != %x" % (result2, data2))



class TestPIMem(unittest.TestCase):

    def test_pi_mem(self):

        dut = TestMemoryPortInterface(regwid=64)
        #vl = rtlil.convert(dut, ports=dut.ports())
        #with open("test_basic_l0_cache.il", "w") as f:
        #    f.write(vl)

        run_simulation(dut, {"sync": l0_cache_ldst(self, dut)},
                       vcd_name='test_pi_mem_basic.vcd')

    def test_pi2ls(self):
        m = Module()
        regwid = 64
        addrwid = 48
        m.submodules.dut = dut = Pi2LSUI("mem", regwid=regwid, addrwid=addrwid)
        m.submodules.lsmem = lsmem = TestMemLoadStoreUnit(addr_wid=addrwid,
                                                          mask_wid=8,
                                                          data_wid=regwid)

        # Connect inputs
        m.d.comb += [lsmem.x_addr_i.eq(dut.lsui.x_addr_i),
                     lsmem.x_mask_i.eq(dut.lsui.x_mask_i),
                     lsmem.x_ld_i.eq(dut.lsui.x_ld_i),
                     lsmem.x_st_i.eq(dut.lsui.x_st_i),
                     lsmem.x_st_data_i.eq(dut.lsui.x_st_data_i),
                     lsmem.x_stall_i.eq(dut.lsui.x_stall_i),
                     lsmem.x_valid_i.eq(dut.lsui.x_valid_i),
                     lsmem.m_stall_i.eq(dut.lsui.m_stall_i),
                     lsmem.m_valid_i.eq(dut.lsui.m_valid_i)]

        m.d.comb += [dut.lsui.x_busy_o.eq(lsmem.x_busy_o),
                     dut.lsui.m_busy_o.eq(lsmem.m_busy_o),
                     dut.lsui.m_ld_data_o.eq(lsmem.m_ld_data_o),
                     dut.lsui.m_load_err_o.eq(lsmem.m_load_err_o),
                     dut.lsui.m_store_err_o.eq(lsmem.m_store_err_o),
                     dut.lsui.m_badaddr_o.eq(lsmem.m_badaddr_o)]

        run_simulation(m, {"sync": l0_cache_ldst(self, dut)},
                       vcd_name='test_pi2ls.vcd')

if __name__ == '__main__':
    unittest.main(exit=False)
