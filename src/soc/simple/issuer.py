"""simple core issuer

not in any way intended for production use.  this runs a FSM that:

* reads the Program Counter from FastRegs
* reads an instruction from a fixed-size Test Memory
* issues it to the Simple Core
* waits for it to complete
* increments the PC
* does it all over again

the purpose of this module is to verify the functional correctness
of the Function Units in the absolute simplest and clearest possible
way, and to at provide something that can be further incrementally
improved.
"""

from nmigen import (Elaboratable, Module, Signal, ClockSignal, ResetSignal,
                    ClockDomain, DomainRenamer)
from nmigen.cli import rtlil
from nmigen.cli import main
import sys

from soc.decoder.decode2execute1 import Data
from soc.experiment.testmem import TestMemory # test only for instructions
from soc.regfile.regfiles import FastRegs
from soc.simple.core import NonProductionCore
from soc.config.test.test_loadstore import TestMemPspec
from soc.config.ifetch import ConfigFetchUnit
from soc.decoder.power_enums import MicrOp
from soc.debug.dmi import CoreDebug, DMIInterface
from soc.config.state import CoreState


class TestIssuer(Elaboratable):
    """TestIssuer - reads instructions from TestMemory and issues them

    efficiency and speed is not the main goal here: functional correctness is.
    """
    def __init__(self, pspec):
        # main instruction core
        self.core = core = NonProductionCore(pspec)

        # Test Instruction memory
        self.imem = ConfigFetchUnit(pspec).fu
        # one-row cache of instruction read
        self.iline = Signal(64) # one instruction line
        self.iprev_adr = Signal(64) # previous address: if different, do read

        # DMI interface
        self.dbg = CoreDebug()

        # instruction go/monitor
        self.pc_o = Signal(64, reset_less=True)
        self.pc_i = Data(64, "pc_i") # set "ok" to indicate "please change me"
        self.core_bigendian_i = Signal()
        self.busy_o = Signal(reset_less=True)
        self.memerr_o = Signal(reset_less=True)

        # FAST regfile read /write ports for PC and MSR
        self.fast_r_pc = self.core.regs.rf['fast'].r_ports['cia'] # PC rd
        self.fast_w_pc = self.core.regs.rf['fast'].w_ports['d_wr1'] # PC wr
        self.fast_r_msr = self.core.regs.rf['fast'].r_ports['msr'] # MSR rd

        # DMI interface access
        self.int_r = self.core.regs.rf['int'].r_ports['dmi'] # INT read

        # hack method of keeping an eye on whether branch/trap set the PC
        self.fast_nia = self.core.regs.rf['fast'].w_ports['nia']
        self.fast_nia.wen.name = 'fast_nia_wen'

    def elaborate(self, platform):
        m = Module()
        comb, sync = m.d.comb, m.d.sync

        m.submodules.core = core = DomainRenamer("coresync")(self.core)
        m.submodules.imem = imem = self.imem
        m.submodules.dbg = dbg = self.dbg

        # convenience
        dmi = dbg.dmi
        d_reg = dbg.dbg_gpr

        # clock delay power-on reset
        cd_por  = ClockDomain(reset_less=True)
        cd_sync = ClockDomain()
        core_sync = ClockDomain("coresync")
        m.domains += cd_por, cd_sync, core_sync

        delay = Signal(range(4), reset=1)
        with m.If(delay != 0):
            m.d.por += delay.eq(delay - 1)
        comb += cd_por.clk.eq(ClockSignal())
        comb += core_sync.clk.eq(ClockSignal())
        # XXX TODO: power-on reset delay (later)
        #comb += core.core_reset_i.eq(delay != 0 | dbg.core_rst_o)

        # busy/halted signals from core
        comb += self.busy_o.eq(core.busy_o)
        comb += core.bigendian_i.eq(self.core_bigendian_i)

        # current state (MSR/PC at the moment
        cur_state = CoreState("cur")

        # temporary hack: says "go" immediately for both address gen and ST
        l0 = core.l0
        ldst = core.fus.fus['ldst0']
        m.d.comb += ldst.ad.go_i.eq(ldst.ad.rel_o) # link addr-go direct to rel
        m.d.comb += ldst.st.go_i.eq(ldst.st.rel_o) # link store-go direct to rel

        # PC and instruction from I-Memory
        current_insn = Signal(32) # current fetched instruction (note sync)
        pc_changed = Signal() # note write to PC
        comb += self.pc_o.eq(cur_state.pc)
        ilatch = Signal(32)

        # MSR
        msr = Signal(64, reset_less=True)

        # next instruction (+4 on current)
        nia = Signal(64, reset_less=True)
        comb += nia.eq(cur_state.pc + 4)

        # read the PC
        pc = Signal(64, reset_less=True)
        with m.If(self.pc_i.ok):
            # incoming override (start from pc_i)
            comb += pc.eq(self.pc_i.data)
        with m.Else():
            # otherwise read FastRegs regfile for PC
            comb += self.fast_r_pc.ren.eq(1<<FastRegs.PC)
            comb += pc.eq(self.fast_r_pc.data_o)

        # connect up debug signals
        # TODO comb += core.icache_rst_i.eq(dbg.icache_rst_o)
        comb += core.core_stopped_i.eq(dbg.core_stop_o)
        comb += core.core_reset_i.eq(dbg.core_rst_o)
        comb += dbg.terminate_i.eq(core.core_terminate_o)
        comb += dbg.state.pc.eq(pc)
        comb += dbg.state.msr.eq(cur_state.msr)

        # temporaries
        core_busy_o = core.busy_o         # core is busy
        core_ivalid_i = core.ivalid_i     # instruction is valid
        core_issue_i = core.issue_i       # instruction is issued
        core_be_i = core.bigendian_i      # bigendian mode
        core_opcode_i = core.raw_opcode_i # raw opcode

        insn_type = core.pdecode2.e.do.insn_type
        insn_state = core.pdecode2.state

        # actually use a nmigen FSM for the first time (w00t)
        # this FSM is perhaps unusual in that it detects conditions
        # then "holds" information, combinatorially, for the core
        # (as opposed to using sync - which would be on a clock's delay)
        # this includes the actual opcode, valid flags and so on.
        with m.FSM() as fsm:

            # waiting (zzz)
            with m.State("IDLE"):
                sync += pc_changed.eq(0)
                with m.If(~dbg.core_stop_o):
                    # instruction allowed to go: start by reading the PC
                    # capture the PC and also drop it into Insn Memory
                    # we have joined a pair of combinatorial memory
                    # lookups together.  this is Generally Bad.
                    comb += self.imem.a_pc_i.eq(pc)
                    comb += self.imem.a_valid_i.eq(1)
                    comb += self.imem.f_valid_i.eq(1)
                    sync += cur_state.pc.eq(pc)
                    m.next = "INSN_READ" # move to "wait for bus" phase

            # waiting for instruction bus (stays there until not busy)
            with m.State("INSN_READ"):
                with m.If(self.imem.f_busy_o): # zzz...
                    # busy: stay in wait-read
                    comb += self.imem.a_valid_i.eq(1)
                    comb += self.imem.f_valid_i.eq(1)
                with m.Else():
                    # not busy: instruction fetched
                    f_instr_o = self.imem.f_instr_o
                    if f_instr_o.width == 32:
                        insn = f_instr_o
                    else:
                        insn = f_instr_o.word_select(cur_state.pc[2], 32)
                    comb += current_insn.eq(insn)
                    comb += core_ivalid_i.eq(1) # instruction is valid
                    comb += core_issue_i.eq(1)  # and issued
                    comb += core_opcode_i.eq(current_insn) # actual opcode
                    sync += ilatch.eq(current_insn) # latch current insn

                    # read MSR, latch it, and put it in decode "state"
                    comb += self.fast_r_msr.ren.eq(1<<FastRegs.MSR)
                    comb += msr.eq(self.fast_r_msr.data_o)
                    comb += insn_state.msr.eq(msr)
                    sync += cur_state.msr.eq(msr) # latch current MSR

                    # also drop PC into decode "state"
                    comb += insn_state.pc.eq(cur_state.pc)

                    m.next = "INSN_ACTIVE" # move to "wait completion"

            # instruction started: must wait till it finishes
            with m.State("INSN_ACTIVE"):
                with m.If(insn_type != MicrOp.OP_NOP):
                    comb += core_ivalid_i.eq(1) # instruction is valid
                comb += core_opcode_i.eq(ilatch) # actual opcode
                comb += insn_state.eq(cur_state)     # and MSR and PC
                with m.If(self.fast_nia.wen):
                    sync += pc_changed.eq(1)
                with m.If(~core_busy_o): # instruction done!
                    # ok here we are not reading the branch unit.  TODO
                    # this just blithely overwrites whatever pipeline
                    # updated the PC
                    with m.If(~pc_changed):
                        comb += self.fast_w_pc.wen.eq(1<<FastRegs.PC)
                        comb += self.fast_w_pc.data_i.eq(nia)
                    m.next = "IDLE" # back to idle

        # this bit doesn't have to be in the FSM: connect up to read
        # regfiles on demand from DMI

        with m.If(d_reg.req): # request for regfile access being made
            # TODO: error-check this
            # XXX should this be combinatorial?  sync better?
            comb += self.int_r.ren.eq(1<<d_reg.addr)
            comb += d_reg.data.eq(self.int_r.data_o)
            comb += d_reg.ack.eq(1)

        return m

    def __iter__(self):
        yield from self.pc_i.ports()
        yield self.pc_o
        yield self.memerr_o
        yield from self.core.ports()
        yield from self.imem.ports()
        yield self.core_bigendian_i
        yield self.busy_o

    def ports(self):
        return list(self)

    def external_ports(self):
        return self.pc_i.ports() + [self.pc_o,
                                    self.memerr_o,
                                    self.core_bigendian_i,
                                    ClockSignal(),
                                    ResetSignal(),
                                    self.busy_o,
                                    ] + \
                list(self.dbg.dmi.ports()) + \
                list(self.imem.ibus.fields.values()) + \
                list(self.core.l0.cmpi.lsmem.lsi.dbus.fields.values())

    def ports(self):
        return list(self)


if __name__ == '__main__':
    units = {'alu': 1, 'cr': 1, 'branch': 1, 'trap': 1, 'logical': 1,
             'spr': 1,
             'div': 1,
             'mul': 1,
             'shiftrot': 1}
    pspec = TestMemPspec(ldst_ifacetype='bare_wb',
                         imem_ifacetype='bare_wb',
                         addr_wid=48,
                         mask_wid=8,
                         reg_wid=64,
                         units=units)
    dut = TestIssuer(pspec)
    vl = main(dut, ports=dut.ports(), name="test_issuer")

    if len(sys.argv) == 1:
        vl = rtlil.convert(dut, ports=dut.external_ports(), name="test_issuer")
        with open("test_issuer.il", "w") as f:
            f.write(vl)
