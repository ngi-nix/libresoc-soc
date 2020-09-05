"""simple core issuer

not in any way intended for production use.  this runs a FSM that:

* reads the Program Counter from StateRegs
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

from soc.decoder.power_decoder import create_pdecode
from soc.decoder.power_decoder2 import PowerDecode2
from soc.decoder.decode2execute1 import Data
from soc.experiment.testmem import TestMemory # test only for instructions
from soc.regfile.regfiles import StateRegs
from soc.simple.core import NonProductionCore
from soc.config.test.test_loadstore import TestMemPspec
from soc.config.ifetch import ConfigFetchUnit
from soc.decoder.power_enums import MicrOp
from soc.debug.dmi import CoreDebug, DMIInterface
from soc.config.state import CoreState
from soc.interrupts.xics import XICS_ICP, XICS_ICS
from soc.bus.simple_gpio import SimpleGPIO

from nmutil.util import rising_edge


class TestIssuer(Elaboratable):
    """TestIssuer - reads instructions from TestMemory and issues them

    efficiency and speed is not the main goal here: functional correctness is.
    """
    def __init__(self, pspec):

        # add interrupt controller?
        self.xics = hasattr(pspec, "xics") and pspec.xics == True
        if self.xics:
            self.xics_icp = XICS_ICP()
            self.xics_ics = XICS_ICS()
            self.int_level_i = self.xics_ics.int_level_i

        # add GPIO peripheral?
        self.gpio = hasattr(pspec, "gpio") and pspec.gpio == True
        if self.gpio:
            self.simple_gpio = SimpleGPIO()
            self.gpio_o = self.simple_gpio.gpio_o

        # main instruction core
        self.core = core = NonProductionCore(pspec)

        # instruction decoder
        pdecode = create_pdecode()
        self.pdecode2 = PowerDecode2(pdecode)   # decoder

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
        staterf = self.core.regs.rf['state']
        self.state_r_pc = staterf.r_ports['cia'] # PC rd
        self.state_w_pc = staterf.w_ports['d_wr1'] # PC wr
        self.state_r_msr = staterf.r_ports['msr'] # MSR rd

        # DMI interface access
        intrf = self.core.regs.rf['int']
        crrf = self.core.regs.rf['cr']
        xerrf = self.core.regs.rf['xer']
        self.int_r = intrf.r_ports['dmi'] # INT read
        self.cr_r = crrf.r_ports['full_cr_dbg'] # CR read
        self.xer_r = xerrf.r_ports['full_xer'] # XER read

        # hack method of keeping an eye on whether branch/trap set the PC
        self.state_nia = self.core.regs.rf['state'].w_ports['nia']
        self.state_nia.wen.name = 'state_nia_wen'

    def elaborate(self, platform):
        m = Module()
        comb, sync = m.d.comb, m.d.sync

        m.submodules.core = core = DomainRenamer("coresync")(self.core)
        m.submodules.imem = imem = self.imem
        m.submodules.dbg = dbg = self.dbg

        # current state (MSR/PC at the moment
        cur_state = CoreState("cur")

        # XICS interrupt handler
        if self.xics:
            m.submodules.xics_icp = icp = self.xics_icp
            m.submodules.xics_ics = ics = self.xics_ics
            comb += icp.ics_i.eq(ics.icp_o)           # connect ICS to ICP
            sync += cur_state.eint.eq(icp.core_irq_o) # connect ICP to core

        # GPIO test peripheral
        if self.gpio:
            m.submodules.simple_gpio = simple_gpio = self.simple_gpio

        # connect one GPIO output to ICS bit 5 (like in microwatt soc.vhdl)
        if self.gpio and self.xics:
            comb += self.int_level_i[5].eq(simple_gpio.gpio_o[0])

        # instruction decoder
        pdecode = create_pdecode()
        m.submodules.dec2 = pdecode2 = self.pdecode2

        # convenience
        dmi, d_reg, d_cr, d_xer, = dbg.dmi, dbg.d_gpr, dbg.d_cr, dbg.d_xer
        intrf = self.core.regs.rf['int']

        # clock delay power-on reset
        cd_por  = ClockDomain(reset_less=True)
        cd_sync = ClockDomain()
        core_sync = ClockDomain("coresync")
        m.domains += cd_por, cd_sync, core_sync

        delay = Signal(range(4), reset=3)
        with m.If(delay != 0):
            m.d.por += delay.eq(delay - 1)
        comb += cd_por.clk.eq(ClockSignal())
        comb += core_sync.clk.eq(ClockSignal())
        # power-on reset delay 
        comb += core.core_reset_i.eq(delay != 0 | dbg.core_rst_o)

        # busy/halted signals from core
        comb += self.busy_o.eq(core.busy_o)
        comb += pdecode2.dec.bigendian.eq(self.core_bigendian_i)

        # temporary hack: says "go" immediately for both address gen and ST
        l0 = core.l0
        ldst = core.fus.fus['ldst0']
        st_go_edge = rising_edge(m, ldst.st.rel_o)
        m.d.comb += ldst.ad.go_i.eq(ldst.ad.rel_o) # link addr-go direct to rel
        m.d.comb += ldst.st.go_i.eq(st_go_edge) # link store-go to rising rel

        # PC and instruction from I-Memory
        pc_changed = Signal() # note write to PC
        comb += self.pc_o.eq(cur_state.pc)
        ilatch = Signal(32)

        # next instruction (+4 on current)
        nia = Signal(64, reset_less=True)
        comb += nia.eq(cur_state.pc + 4)

        # read the PC
        pc = Signal(64, reset_less=True)
        pc_ok_delay = Signal()
        sync += pc_ok_delay.eq(~self.pc_i.ok)
        with m.If(self.pc_i.ok):
            # incoming override (start from pc_i)
            comb += pc.eq(self.pc_i.data)
        with m.Else():
            # otherwise read StateRegs regfile for PC...
            comb += self.state_r_pc.ren.eq(1<<StateRegs.PC)
        # ... but on a 1-clock delay
        with m.If(pc_ok_delay):
            comb += pc.eq(self.state_r_pc.data_o)

        # don't write pc every cycle
        comb += self.state_w_pc.wen.eq(0)
        comb += self.state_w_pc.data_i.eq(0)

        # don't read msr every cycle
        comb += self.state_r_msr.ren.eq(0)
        msr_read = Signal(reset=1)

        # connect up debug signals
        # TODO comb += core.icache_rst_i.eq(dbg.icache_rst_o)
        comb += dbg.terminate_i.eq(core.core_terminate_o)
        comb += dbg.state.pc.eq(pc)
        #comb += dbg.state.pc.eq(cur_state.pc)
        comb += dbg.state.msr.eq(cur_state.msr)

        # temporaries
        core_busy_o = core.busy_o                 # core is busy
        core_ivalid_i = core.ivalid_i             # instruction is valid
        core_issue_i = core.issue_i               # instruction is issued
        dec_opcode_i = pdecode2.dec.raw_opcode_in # raw opcode

        insn_type = core.e.do.insn_type
        dec_state = pdecode2.state

        # actually use a nmigen FSM for the first time (w00t)
        # this FSM is perhaps unusual in that it detects conditions
        # then "holds" information, combinatorially, for the core
        # (as opposed to using sync - which would be on a clock's delay)
        # this includes the actual opcode, valid flags and so on.
        with m.FSM() as fsm:

            # waiting (zzz)
            with m.State("IDLE"):
                sync += pc_changed.eq(0)
                sync += core.e.eq(0)
                with m.If(~dbg.core_stop_o & ~core.core_reset_i):
                    # instruction allowed to go: start by reading the PC
                    # capture the PC and also drop it into Insn Memory
                    # we have joined a pair of combinatorial memory
                    # lookups together.  this is Generally Bad.
                    comb += self.imem.a_pc_i.eq(pc)
                    comb += self.imem.a_valid_i.eq(1)
                    comb += self.imem.f_valid_i.eq(1)
                    sync += cur_state.pc.eq(pc)

                    # initiate read of MSR
                    comb += self.state_r_msr.ren.eq(1<<StateRegs.MSR)
                    sync += msr_read.eq(0)

                    m.next = "INSN_READ" # move to "wait for bus" phase
                with m.Else():
                    comb += core.core_stopped_i.eq(1)
                    comb += dbg.core_stopped_i.eq(1)

            # dummy pause to find out why simulation is not keeping up
            with m.State("INSN_READ"):
                # one cycle later, msr read arrives
                with m.If(~msr_read):
                    sync += msr_read.eq(1)
                    sync += cur_state.msr.eq(self.state_r_msr.data_o)
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
                    comb += dec_opcode_i.eq(insn) # actual opcode
                    comb += dec_state.eq(cur_state)
                    sync += core.e.eq(pdecode2.e)
                    sync += ilatch.eq(insn) # latch current insn
                    # also drop PC and MSR into decode "state"
                    m.next = "INSN_START" # move to "start"

            # waiting for instruction bus (stays there until not busy)
            with m.State("INSN_START"):
                comb += core_ivalid_i.eq(1) # instruction is valid
                comb += core_issue_i.eq(1)  # and issued


                m.next = "INSN_ACTIVE" # move to "wait completion"

            # instruction started: must wait till it finishes
            with m.State("INSN_ACTIVE"):
                with m.If(insn_type != MicrOp.OP_NOP):
                    comb += core_ivalid_i.eq(1) # instruction is valid
                with m.If(self.state_nia.wen & (1<<StateRegs.PC)):
                    sync += pc_changed.eq(1)
                with m.If(~core_busy_o): # instruction done!
                    # ok here we are not reading the branch unit.  TODO
                    # this just blithely overwrites whatever pipeline
                    # updated the PC
                    with m.If(~pc_changed):
                        comb += self.state_w_pc.wen.eq(1<<StateRegs.PC)
                        comb += self.state_w_pc.data_i.eq(nia)
                    sync += core.e.eq(0)
                    m.next = "IDLE" # back to idle

        # this bit doesn't have to be in the FSM: connect up to read
        # regfiles on demand from DMI
        with m.If(d_reg.req): # request for regfile access being made
            # TODO: error-check this
            # XXX should this be combinatorial?  sync better?
            if intrf.unary:
                comb += self.int_r.ren.eq(1<<d_reg.addr)
            else:
                comb += self.int_r.addr.eq(d_reg.addr)
                comb += self.int_r.ren.eq(1)
        d_reg_delay  = Signal()
        sync += d_reg_delay.eq(d_reg.req)
        with m.If(d_reg_delay):
            # data arrives one clock later
            comb += d_reg.data.eq(self.int_r.data_o)
            comb += d_reg.ack.eq(1)

        # sigh same thing for CR debug
        with m.If(d_cr.req): # request for regfile access being made
            comb += self.cr_r.ren.eq(0b11111111) # enable all
        d_cr_delay  = Signal()
        sync += d_cr_delay.eq(d_cr.req)
        with m.If(d_cr_delay):
            # data arrives one clock later
            comb += d_cr.data.eq(self.cr_r.data_o)
            comb += d_cr.ack.eq(1)

        # aaand XER...
        with m.If(d_xer.req): # request for regfile access being made
            comb += self.xer_r.ren.eq(0b111111) # enable all
        d_xer_delay  = Signal()
        sync += d_xer_delay.eq(d_xer.req)
        with m.If(d_xer_delay):
            # data arrives one clock later
            comb += d_xer.data.eq(self.xer_r.data_o)
            comb += d_xer.ack.eq(1)

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
        ports = self.pc_i.ports()
        ports += [self.pc_o, self.memerr_o, self.core_bigendian_i, self.busy_o,
                  ClockSignal(), ResetSignal(),
                ]
        ports += list(self.dbg.dmi.ports())
        ports += list(self.imem.ibus.fields.values())
        ports += list(self.core.l0.cmpi.lsmem.lsi.slavebus.fields.values())

        if self.xics:
            ports += list(self.xics_icp.bus.fields.values())
            ports += list(self.xics_ics.bus.fields.values())
            ports.append(self.int_level_i)

        if self.gpio:
            ports += list(self.simple_gpio.bus.fields.values())
            ports.append(self.gpio_o)

        return ports

    def ports(self):
        return list(self)


if __name__ == '__main__':
    units = {'alu': 1, 'cr': 1, 'branch': 1, 'trap': 1, 'logical': 1,
             'spr': 1,
             'div': 1,
             'mul': 1,
             'shiftrot': 1
            }
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
