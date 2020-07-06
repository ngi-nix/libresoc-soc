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

from nmigen import Elaboratable, Module, Signal
from nmigen.cli import rtlil

from soc.decoder.decode2execute1 import Data
from soc.experiment.testmem import TestMemory # test only for instructions
from soc.regfile.regfiles import FastRegs
from soc.simple.core import NonProductionCore
from soc.config.test.test_loadstore import TestMemPspec
from soc.config.ifetch import ConfigFetchUnit


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

        # instruction go/monitor
        self.go_insn_i = Signal(reset_less=True)
        self.pc_o = Signal(64, reset_less=True)
        self.pc_i = Data(64, "pc") # set "ok" to indicate "please change me"
        self.busy_o = core.busy_o
        self.memerr_o = Signal(reset_less=True)

        # FAST regfile read /write ports
        self.fast_rd1 = self.core.regs.rf['fast'].r_ports['d_rd1']
        self.fast_wr1 = self.core.regs.rf['fast'].w_ports['d_wr1']
        # hack method of keeping an eye on whether branch/trap set the PC
        self.fast_nia = self.core.regs.rf['fast'].w_ports['nia']
        self.fast_nia.wen.name = 'fast_nia_wen'

    def elaborate(self, platform):
        m = Module()
        comb, sync = m.d.comb, m.d.sync

        m.submodules.core = core = self.core
        m.submodules.imem = imem = self.imem

        # temporary hack: says "go" immediately for both address gen and ST
        l0 = core.l0
        ldst = core.fus.fus['ldst0']
        m.d.comb += ldst.ad.go.eq(ldst.ad.rel) # link addr-go direct to rel
        m.d.comb += ldst.st.go.eq(ldst.st.rel) # link store-go direct to rel

        # PC and instruction from I-Memory
        current_insn = Signal(32) # current fetched instruction (note sync)
        current_pc = Signal(64) # current PC (note it is reset/sync)
        pc_changed = Signal() # note write to PC
        comb += self.pc_o.eq(current_pc)
        ilatch = Signal(32)

        # next instruction (+4 on current)
        nia = Signal(64, reset_less=True)
        comb += nia.eq(current_pc + 4)

        # temporaries
        core_busy_o = core.busy_o         # core is busy
        core_ivalid_i = core.ivalid_i     # instruction is valid
        core_issue_i = core.issue_i       # instruction is issued
        core_be_i = core.bigendian_i      # bigendian mode
        core_opcode_i = core.raw_opcode_i # raw opcode

        # actually use a nmigen FSM for the first time (w00t)
        with m.FSM() as fsm:

            # waiting (zzz)
            with m.State("IDLE"):
                sync += pc_changed.eq(0)
                with m.If(self.go_insn_i):
                    # instruction allowed to go: start by reading the PC
                    pc = Signal(64, reset_less=True)
                    with m.If(self.pc_i.ok):
                        # incoming override (start from pc_i)
                        comb += pc.eq(self.pc_i.data)
                    with m.Else():
                        # otherwise read FastRegs regfile for PC
                        comb += self.fast_rd1.ren.eq(1<<FastRegs.PC)
                        comb += pc.eq(self.fast_rd1.data_o)
                    # capture the PC and also drop it into Insn Memory
                    # we have joined a pair of combinatorial memory
                    # lookups together.  this is Generally Bad.
                    comb += self.imem.a_pc_i.eq(pc)
                    comb += self.imem.a_valid_i.eq(1)
                    comb += self.imem.f_valid_i.eq(1)
                    sync += current_pc.eq(pc)
                    m.next = "INSN_READ" # move to "wait for bus" phase

            # waiting for instruction bus (stays there until not busy)
            with m.State("INSN_READ"):
                with m.If(self.imem.f_busy_o): # zzz...
                    # busy: stay in wait-read
                    comb += self.imem.a_valid_i.eq(1)
                    comb += self.imem.f_valid_i.eq(1)
                with m.Else():
                    # not busy: instruction fetched
                    insn = self.imem.f_instr_o.word_select(current_pc[2], 32)
                    comb += current_insn.eq(insn)
                    comb += core_ivalid_i.eq(1) # say instruction is valid
                    comb += core_issue_i.eq(1)  # and issued (ivalid redundant)
                    comb += core_be_i.eq(0)     # little-endian mode
                    comb += core_opcode_i.eq(current_insn) # actual opcode
                    sync += ilatch.eq(current_insn)
                    m.next = "INSN_ACTIVE" # move to "wait for completion" phase

            # instruction started: must wait till it finishes
            with m.State("INSN_ACTIVE"):
                comb += core_ivalid_i.eq(1) # say instruction is valid
                comb += core_opcode_i.eq(ilatch) # actual opcode
                #sync += core_issue_i.eq(0) # issue raises for only one cycle
                with m.If(self.fast_nia.wen):
                    sync += pc_changed.eq(1)
                with m.If(~core_busy_o): # instruction done!
                    #sync += core_ivalid_i.eq(0) # say instruction is invalid
                    #sync += core_opcode_i.eq(0) # clear out (no good reason)
                    # ok here we are not reading the branch unit.  TODO
                    # this just blithely overwrites whatever pipeline updated
                    # the PC
                    with m.If(~pc_changed):
                        comb += self.fast_wr1.wen.eq(1<<FastRegs.PC)
                        comb += self.fast_wr1.data_i.eq(nia)
                    m.next = "IDLE" # back to idle

        return m

    def __iter__(self):
        yield from self.pc_i.ports()
        yield self.pc_o
        yield self.go_insn_i
        yield self.memerr_o
        yield from self.core.ports()
        yield from self.imem.ports()

    def ports(self):
        return list(self)


if __name__ == '__main__':
    units = {'alu': 1, 'cr': 1, 'branch': 1, 'trap': 1, 'logical': 1,
             'spr': 1,
             'mul': 1,
             'shiftrot': 1}
    pspec = TestMemPspec(ldst_ifacetype='bare_wb',
                         imem_ifacetype='bare_wb',
                         addr_wid=48,
                         mask_wid=8,
                         reg_wid=64,
                         units=units)
    dut = TestIssuer(pspec)
    vl = rtlil.convert(dut, ports=dut.ports(), name="test_issuer")
    with open("test_issuer.il", "w") as f:
        f.write(vl)

