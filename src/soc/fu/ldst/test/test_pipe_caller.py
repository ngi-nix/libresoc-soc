from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmigen.cli import rtlil
import unittest
from soc.decoder.isa.caller import special_sprs
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.decoder.power_enums import (XER_bits, Function, MicrOp, CryIn)
from soc.decoder.selectable_int import SelectableInt
from soc.simulator.program import Program
from soc.decoder.isa.all import ISA
from soc.config.endian import bigendian


from soc.fu.test.common import TestAccumulatorBase, TestCase
from soc.fu.ldst.pipe_data import LDSTPipeSpec
import random


def get_cu_inputs(dec2, sim):
    """naming (res) must conform to LDSTFunctionUnit input regspec
    """
    res = {}

    # RA
    reg1_ok = yield dec2.e.read_reg1.ok
    if reg1_ok:
        data1 = yield dec2.e.read_reg1.data
        res['ra'] = sim.gpr(data1).value

    # RB (or immediate)
    reg2_ok = yield dec2.e.read_reg2.ok
    if reg2_ok:
        data2 = yield dec2.e.read_reg2.data
        res['rb'] = sim.gpr(data2).value

    # RC
    reg3_ok = yield dec2.e.read_reg3.ok
    if reg3_ok:
        data3 = yield dec2.e.read_reg3.data
        res['rc'] = sim.gpr(data3).value

    # XER.so
    oe = yield dec2.e.do.oe.data[0] & dec2.e.do.oe.ok
    if oe:
        so = 1 if sim.spr['XER'][XER_bits['SO']] else 0
        res['xer_so'] = so

    return res


class LDSTTestCase(TestAccumulatorBase):

    def case_1_load(self):
        lst = ["lhz 3, 0(1)"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x0004
        initial_regs[2] = 0x0008
        initial_mem = {0x0000: (0x5432123412345678, 8),
                       0x0008: (0xabcdef0187654321, 8),
                       0x0020: (0x1828384822324252, 8),
                        }
        self.add_case(Program(lst, bigendian), initial_regs,
                             initial_mem=initial_mem)

    def case_2_load_store(self):
        lst = [
               "stb 3, 1(2)",
               "lbz 4, 1(2)",
        ]
        initial_regs = [0] * 32
        initial_regs[1] = 0x0004
        initial_regs[2] = 0x0008
        initial_regs[3] = 0x00ee
        initial_mem = {0x0000: (0x5432123412345678, 8),
                       0x0008: (0xabcdef0187654321, 8),
                       0x0020: (0x1828384822324252, 8),
                        }
        self.add_case(Program(lst, bigendian), initial_regs,
                             initial_mem=initial_mem)

    def case_3_load_store(self):
        lst = ["sth 4, 0(2)",
               "lhz 4, 0(2)"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x0004
        initial_regs[2] = 0x0002
        initial_regs[3] = 0x15eb
        initial_mem = {0x0000: (0x5432123412345678, 8),
                       0x0008: (0xabcdef0187654321, 8),
                       0x0020: (0x1828384822324252, 8),
                        }
        self.add_case(Program(lst, bigendian), initial_regs,
                             initial_mem=initial_mem)

    def case_4_load_store_rev_ext(self):
        lst = ["stwx 1, 4, 2",
               "lwbrx 3, 4, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x5678
        initial_regs[2] = 0x001c
        initial_regs[4] = 0x0008
        initial_mem = {0x0000: (0x5432123412345678, 8),
                       0x0008: (0xabcdef0187654321, 8),
                       0x0020: (0x1828384822324252, 8),
                        }
        self.add_case(Program(lst, bigendian), initial_regs,
                             initial_mem=initial_mem)

    def case_5_load_store_rev_ext(self):
        lst = ["stwbrx 1, 4, 2",
               "lwzx 3, 4, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x5678
        initial_regs[2] = 0x001c
        initial_regs[4] = 0x0008
        initial_mem = {0x0000: (0x5432123412345678, 8),
                       0x0008: (0xabcdef0187654321, 8),
                       0x0020: (0x1828384822324252, 8),
                        }
        self.add_case(Program(lst, bigendian), initial_regs,
                             initial_mem=initial_mem)

    def case_6_load_store_rev_ext(self):
        lst = ["stwbrx 1, 4, 2",
               "lwbrx 3, 4, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x5678
        initial_regs[2] = 0x001c
        initial_regs[4] = 0x0008
        initial_mem = {0x0000: (0x5432123412345678, 8),
                       0x0008: (0xabcdef0187654321, 8),
                       0x0020: (0x1828384822324252, 8),
                        }
        self.add_case(Program(lst, bigendian), initial_regs,
                             initial_mem=initial_mem)

    def case_7_load_store_d(self):
        lst = [
               "std 3, 0(2)",
               "ld 4, 0(2)",
        ]
        initial_regs = [0] * 32
        initial_regs[1] = 0x0004
        initial_regs[2] = 0x0008
        initial_regs[3] = 0x00ee
        initial_mem = {0x0000: (0x5432123412345678, 8),
                       0x0008: (0xabcdef0187654321, 8),
                       0x0020: (0x1828384822324252, 8),
                        }
        self.add_case(Program(lst, bigendian), initial_regs,
                             initial_mem=initial_mem)

    def case_8_load_store_d_update(self):
        lst = [
               "stdu 3, 0(2)",
               "ld 4, 0(2)",
        ]
        initial_regs = [0] * 32
        initial_regs[1] = 0x0004
        initial_regs[2] = 0x0008
        initial_regs[3] = 0x00ee
        initial_mem = {0x0000: (0x5432123412345678, 8),
                       0x0008: (0xabcdef0187654321, 8),
                       0x0020: (0x1828384822324252, 8),
                        }
        self.add_case(Program(lst, bigendian), initial_regs,
                             initial_mem=initial_mem)

