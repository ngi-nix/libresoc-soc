"""MMU TestRunner class, runs TestIssuer instructions using a wishbone ROM

related bugs:

 * https://bugs.libre-soc.org/show_bug.cgi?id=363
"""
from nmigen import Module, Signal, Cat, ClockSignal

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git
from nmutil.sim_tmp_alternative import Simulator, Settle

from nmutil.formaltest import FHDLTestCase
from nmutil.gtkw import write_gtkw
from nmigen.cli import rtlil
from soc.decoder.isa.caller import special_sprs, SVP64State
from soc.decoder.isa.all import ISA
from soc.config.endian import bigendian

from soc.decoder.power_decoder import create_pdecode
from soc.decoder.power_decoder2 import PowerDecode2
from soc.regfile.regfiles import StateRegs

from soc.simple.issuer import TestIssuerInternal

from soc.config.test.test_loadstore import TestMemPspec
from soc.simple.test.test_core import (setup_regs, check_regs,
                                       wait_for_busy_clear,
                                       wait_for_busy_hi)
from soc.fu.compunits.test.test_compunit import (setup_test_memory,
                                                 check_sim_memory)
from soc.debug.dmi import DBGCore, DBGCtrl, DBGStat
from nmutil.util import wrap
from soc.experiment.test.test_mmu_dcache import (set_stop, wb_get)
from soc.simple.test.test_runner import set_dmi, get_dmi
from soc.simple.test.test_runner import setup_i_memory
from soc.simple.test.test_runner import TestRunner

# tobias please don't do massive duplication of code.  modify the existing code
# to add extra options, make sure those options have "no effect".
