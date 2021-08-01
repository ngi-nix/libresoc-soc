"""TestRunner class, runs TestIssuer instructions

related bugs:

 * https://bugs.libre-soc.org/show_bug.cgi?id=363
"""
from nmigen import Module, Signal, Cat, ClockSignal
from nmigen.hdl.xfrm import ResetInserter

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git
from nmutil.sim_tmp_alternative import Simulator, Settle

from nmutil.formaltest import FHDLTestCase
from nmutil.gtkw import write_gtkw
from nmigen.cli import rtlil
from openpower.decoder.isa.caller import special_sprs, SVP64State
from openpower.decoder.isa.all import ISA
from openpower.endian import bigendian

from openpower.decoder.power_decoder import create_pdecode
from openpower.decoder.power_decoder2 import PowerDecode2
from soc.regfile.regfiles import StateRegs

from soc.simple.issuer import TestIssuerInternal

from soc.config.test.test_loadstore import TestMemPspec
from soc.simple.test.test_core import (setup_regs, check_regs,
                                       wait_for_busy_clear,
                                       wait_for_busy_hi)
from soc.fu.compunits.test.test_compunit import (setup_tst_memory,
                                                 check_sim_memory)
from soc.debug.dmi import DBGCore, DBGCtrl, DBGStat
from nmutil.util import wrap
from soc.experiment.test.test_mmu_dcache import wb_get


def setup_i_memory(imem, startaddr, instructions):
    mem = imem
    print("insn before, init mem", mem.depth, mem.width, mem,
          len(instructions))
    for i in range(mem.depth):
        yield mem._array[i].eq(0)
    yield Settle()
    startaddr //= 4  # instructions are 32-bit
    if mem.width == 32:
        mask = ((1 << 32)-1)
        for ins in instructions:
            if isinstance(ins, tuple):
                insn, code = ins
            else:
                insn, code = ins, ''
            insn = insn & 0xffffffff
            yield mem._array[startaddr].eq(insn)
            yield Settle()
            if insn != 0:
                print("instr: %06x 0x%x %s" % (4*startaddr, insn, code))
            startaddr += 1
            startaddr = startaddr & mask
        return

    # 64 bit
    mask = ((1 << 64)-1)
    for ins in instructions:
        if isinstance(ins, tuple):
            insn, code = ins
        else:
            insn, code = ins, ''
        insn = insn & 0xffffffff
        msbs = (startaddr >> 1) & mask
        val = yield mem._array[msbs]
        if insn != 0:
            print("before set", hex(4*startaddr),
                  hex(msbs), hex(val), hex(insn))
        lsb = 1 if (startaddr & 1) else 0
        val = (val | (insn << (lsb*32)))
        val = val & mask
        yield mem._array[msbs].eq(val)
        yield Settle()
        if insn != 0:
            print("after  set", hex(4*startaddr), hex(msbs), hex(val))
            print("instr: %06x 0x%x %s %08x" % (4*startaddr, insn, code, val))
        startaddr += 1
        startaddr = startaddr & mask


def set_dmi(dmi, addr, data):
    yield dmi.req_i.eq(1)
    yield dmi.addr_i.eq(addr)
    yield dmi.din.eq(data)
    yield dmi.we_i.eq(1)
    while True:
        ack = yield dmi.ack_o
        if ack:
            break
        yield
    yield
    yield dmi.req_i.eq(0)
    yield dmi.addr_i.eq(0)
    yield dmi.din.eq(0)
    yield dmi.we_i.eq(0)
    yield


def get_dmi(dmi, addr):
    yield dmi.req_i.eq(1)
    yield dmi.addr_i.eq(addr)
    yield dmi.din.eq(0)
    yield dmi.we_i.eq(0)
    while True:
        ack = yield dmi.ack_o
        if ack:
            break
        yield
    yield  # wait one
    data = yield dmi.dout  # get data after ack valid for 1 cycle
    yield dmi.req_i.eq(0)
    yield dmi.addr_i.eq(0)
    yield dmi.we_i.eq(0)
    yield
    return data


class TestRunner(FHDLTestCase):
    def __init__(self, tst_data, microwatt_mmu=False, rom=None,
                        svp64=True):
        super().__init__("run_all")
        self.test_data = tst_data
        self.microwatt_mmu = microwatt_mmu
        self.rom = rom
        self.svp64 = svp64

    def run_all(self):
        m = Module()
        comb = m.d.comb
        pc_i = Signal(32)
        svstate_i = Signal(64)

        if self.microwatt_mmu:
            ldst_ifacetype = 'test_mmu_cache_wb'
        else:
            ldst_ifacetype = 'test_bare_wb'
        imem_ifacetype = 'test_bare_wb'

        pspec = TestMemPspec(ldst_ifacetype=ldst_ifacetype,
                             imem_ifacetype=imem_ifacetype,
                             addr_wid=48,
                             mask_wid=8,
                             imem_reg_wid=64,
                             # wb_data_width=32,
                             use_pll=False,
                             nocore=False,
                             xics=False,
                             gpio=False,
                             regreduce=True,
                             svp64=self.svp64,
                             mmu=self.microwatt_mmu,
                             reg_wid=64)
        #hard_reset = Signal(reset_less=True)
        issuer = TestIssuerInternal(pspec)
        # use DMI RESET command instead, this does actually work though
        #issuer = ResetInserter({'coresync': hard_reset,
        #                        'sync': hard_reset})(issuer)
        m.submodules.issuer = issuer
        imem = issuer.imem._get_memory()
        core = issuer.core
        dmi = issuer.dbg.dmi
        pdecode2 = issuer.pdecode2
        l0 = core.l0
        regreduce_en = pspec.regreduce_en == True

        #simdec = create_pdecode()
        simdec2 = PowerDecode2(None, regreduce_en=regreduce_en)
        m.submodules.simdec2 = simdec2  # pain in the neck

        # run core clock at same rate as test clock
        intclk = ClockSignal("coresync")
        comb += intclk.eq(ClockSignal())

        comb += issuer.pc_i.data.eq(pc_i)
        comb += issuer.svstate_i.data.eq(svstate_i)

        # nmigen Simulation
        sim = Simulator(m)
        sim.add_clock(1e-6)

        def process():

            # start in stopped
            yield from set_dmi(dmi, DBGCore.CTRL, 1<<DBGCtrl.STOP)
            yield

            # get each test, completely reset the core, and run it

            for test in self.test_data:

                # set up bigendian (TODO: don't do this, use MSR)
                yield issuer.core_bigendian_i.eq(bigendian)
                yield Settle()

                yield
                yield
                yield
                yield

                print(test.name)
                program = test.program
                with self.subTest(test.name):
                    print("regs", test.regs)
                    print("sprs", test.sprs)
                    print("cr", test.cr)
                    print("mem", test.mem)
                    print("msr", test.msr)
                    print("assem", program.assembly)
                    gen = list(program.generate_instructions())
                    insncode = program.assembly.splitlines()
                    instructions = list(zip(gen, insncode))

                    # set up the Simulator (which must track TestIssuer exactly)
                    sim = ISA(simdec2, test.regs, test.sprs, test.cr, test.mem,
                              test.msr,
                              initial_insns=gen, respect_pc=True,
                              disassembly=insncode,
                              bigendian=bigendian,
                              initial_svstate=test.svstate)

                    # establish the TestIssuer context (mem, regs etc)

                    pc = 0  # start address
                    counter = 0  # test to pause/start

                    yield from setup_i_memory(imem, pc, instructions)
                    yield from setup_tst_memory(l0, sim)
                    yield from setup_regs(pdecode2, core, test)

                    # set PC and SVSTATE
                    yield pc_i.eq(pc)
                    yield issuer.pc_i.ok.eq(1)

                    initial_svstate = test.svstate
                    if isinstance(initial_svstate, int):
                        initial_svstate = SVP64State(initial_svstate)
                    yield svstate_i.eq(initial_svstate.value)
                    yield issuer.svstate_i.ok.eq(1)
                    yield

                    print("instructions", instructions)

                    # run the loop of the instructions on the current test
                    index = sim.pc.CIA.value//4
                    while index < len(instructions):
                        ins, code = instructions[index]

                        print("instruction: 0x{:X}".format(ins & 0xffffffff))
                        print(index, code)

                        if counter == 0:
                            # start the core
                            yield
                            yield from set_dmi(dmi, DBGCore.CTRL,
                                               1<<DBGCtrl.START)
                            yield issuer.pc_i.ok.eq(0) # no change PC after this
                            yield issuer.svstate_i.ok.eq(0) # ditto
                            yield
                            yield

                        counter = counter + 1

                        # wait until executed
                        while not (yield issuer.insn_done):
                            yield

                        # set up simulated instruction (in simdec2)
                        try:
                            yield from sim.setup_one()
                        except KeyError:  # instruction not in imem: stop
                            break
                        yield Settle()

                        # call simulated operation
                        print("sim", code)
                        yield from sim.execute_one()
                        yield Settle()
                        index = sim.pc.CIA.value//4

                        terminated = yield issuer.dbg.terminated_o
                        print("terminated", terminated)

                        if index >= len(instructions):
                            print ("index over, send dmi stop")
                            # stop at end
                            yield from set_dmi(dmi, DBGCore.CTRL,
                                               1<<DBGCtrl.STOP)
                            yield
                            yield

                        # register check
                        yield from check_regs(self, sim, core, test, code)

                        # Memory check
                        yield from check_sim_memory(self, l0, sim, code)

                        terminated = yield issuer.dbg.terminated_o
                        print("terminated(2)", terminated)
                        if terminated:
                            break

                # stop at end
                yield from set_dmi(dmi, DBGCore.CTRL, 1<<DBGCtrl.STOP)
                yield
                yield

                # get CR
                cr = yield from get_dmi(dmi, DBGCore.CR)
                print("after test %s cr value %x" % (test.name, cr))

                # get XER
                xer = yield from get_dmi(dmi, DBGCore.XER)
                print("after test %s XER value %x" % (test.name, xer))

                # test of dmi reg get
                for int_reg in range(32):
                    yield from set_dmi(dmi, DBGCore.GSPR_IDX, int_reg)
                    value = yield from get_dmi(dmi, DBGCore.GSPR_DATA)

                    print("after test %s reg %2d value %x" %
                          (test.name, int_reg, value))

                # pull a reset
                yield from set_dmi(dmi, DBGCore.CTRL, 1<<DBGCtrl.RESET)
                yield

        styles = {
            'dec': {'base': 'dec'},
            'bin': {'base': 'bin'},
            'closed': {'closed': True}
        }

        traces = [
            'clk',
            ('state machines', 'closed', [
                'fetch_pc_valid_i', 'fetch_pc_ready_o',
                'fetch_fsm_state',
                'fetch_insn_valid_o', 'fetch_insn_ready_i',
                'pred_insn_valid_i', 'pred_insn_ready_o',
                'fetch_predicate_state',
                'pred_mask_valid_o', 'pred_mask_ready_i',
                'issue_fsm_state',
                'exec_insn_valid_i', 'exec_insn_ready_o',
                'exec_fsm_state',
                'exec_pc_valid_o', 'exec_pc_ready_i',
                'insn_done', 'core_stop_o', 'pc_i_ok', 'pc_changed',
                'is_last', 'dec2.no_out_vec']),
            {'comment': 'fetch and decode'},
            (None, 'dec', [
                'cia[63:0]', 'nia[63:0]', 'pc[63:0]',
                'cur_pc[63:0]', 'core_core_cia[63:0]']),
            'raw_insn_i[31:0]',
            'raw_opcode_in[31:0]', 'insn_type',
            ('svp64 decoding', 'closed', [
                'svp64_rm[23:0]', ('dec2.extra[8:0]', 'bin'),
                'dec2.sv_rm_dec.mode', 'dec2.sv_rm_dec.predmode',
                'dec2.sv_rm_dec.ptype_in',
                'dec2.sv_rm_dec.dstpred[2:0]', 'dec2.sv_rm_dec.srcpred[2:0]',
                'dstmask[63:0]', 'srcmask[63:0]',
                'dregread[4:0]', 'dinvert',
                'sregread[4:0]', 'sinvert',
                'core.int.pred__addr[4:0]', 'core.int.pred__data_o[63:0]',
                'core.int.pred__ren']),
            ('register augmentation', 'dec', 'closed', [
                {'comment': 'v3.0b registers'},
                'dec2.dec_o.RT[4:0]',
                'dec2.dec_a.RA[4:0]',
                'dec2.dec_b.RB[4:0]',
                ('Rdest', [
                    'dec2.o_svdec.reg_in[4:0]',
                    ('dec2.o_svdec.spec[2:0]', 'bin'),
                    'dec2.o_svdec.reg_out[6:0]']),
                ('Rsrc1', [
                    'dec2.in1_svdec.reg_in[4:0]',
                    ('dec2.in1_svdec.spec[2:0]', 'bin'),
                    'dec2.in1_svdec.reg_out[6:0]']),
                ('Rsrc1', [
                    'dec2.in2_svdec.reg_in[4:0]',
                    ('dec2.in2_svdec.spec[2:0]', 'bin'),
                    'dec2.in2_svdec.reg_out[6:0]']),
                {'comment': 'SVP64 registers'},
                'dec2.rego[6:0]', 'dec2.reg1[6:0]', 'dec2.reg2[6:0]'
            ]),
            {'comment': 'svp64 context'},
            'core_core_vl[6:0]', 'core_core_maxvl[6:0]',
            'core_core_srcstep[6:0]', 'next_srcstep[6:0]',
            'core_core_dststep[6:0]',
            {'comment': 'issue and execute'},
            'core.core_core_insn_type',
            (None, 'dec', [
                'core_rego[6:0]', 'core_reg1[6:0]', 'core_reg2[6:0]']),
            'issue_i', 'busy_o',
            {'comment': 'dmi'},
            'dbg.dmi_req_i', 'dbg.dmi_ack_o',
            {'comment': 'instruction memory'},
            'imem.sram.rdport.memory(0)[63:0]',
            {'comment': 'registers'},
            # match with soc.regfile.regfiles.IntRegs port names
            'core.int.rp_src1.memory(0)[63:0]',
            'core.int.rp_src1.memory(1)[63:0]',
            'core.int.rp_src1.memory(2)[63:0]',
            'core.int.rp_src1.memory(3)[63:0]',
            'core.int.rp_src1.memory(4)[63:0]',
            'core.int.rp_src1.memory(5)[63:0]',
            'core.int.rp_src1.memory(6)[63:0]',
            'core.int.rp_src1.memory(7)[63:0]',
            'core.int.rp_src1.memory(9)[63:0]',
            'core.int.rp_src1.memory(10)[63:0]',
            'core.int.rp_src1.memory(13)[63:0]',
            {'comment': 'memory port interface'},
            'core.l0.pimem.ldst_port0_is_ld_i',
            'core.l0.pimem.ldst_port0_is_st_i',
            'core.l0.pimem.ldst_port0_busy_o',
            'core.l0.pimem.ldst_port0_addr_i[47:0]',
            'core.l0.pimem.ldst_port0_addr_i_ok',
            'core.l0.pimem.ldst_port0_addr_ok_o',
            'core.l0.pimem.ldst_port0_st_data_i[63:0]',
            'core.l0.pimem.ldst_port0_st_data_i_ok',
            'core.l0.pimem.ldst_port0_ld_data_o[63:0]',
            'core.l0.pimem.ldst_port0_ld_data_o_ok'
        ]

        if self.microwatt_mmu:
            traces += [
                {'comment': 'microwatt_mmu'},
                'core.fus.mmu0.alu_mmu0.illegal',
                'core.fus.mmu0.alu_mmu0.debug0[3:0]',
                'core.fus.mmu0.alu_mmu0.mmu.state',
                'core.fus.mmu0.alu_mmu0.mmu.pid[31:0]',
                'core.fus.mmu0.alu_mmu0.mmu.prtbl[63:0]',
                {'comment': 'wishbone_memory'},
                'core.fus.mmu0.alu_mmu0.dcache.stb',
                'core.fus.mmu0.alu_mmu0.dcache.cyc',
                'core.fus.mmu0.alu_mmu0.dcache.we',
                'core.fus.mmu0.alu_mmu0.dcache.ack',
                'core.fus.mmu0.alu_mmu0.dcache.stall,'
            ]

        write_gtkw("issuer_simulator.gtkw",
                   "issuer_simulator.vcd",
                   traces, styles, module='top.issuer')

        # add run of instructions
        sim.add_sync_process(process)

        # optionally, if a wishbone-based ROM is passed in, run that as an
        # extra emulated process
        if self.rom is not None:
            dcache = core.fus.fus["mmu0"].alu.dcache
            default_mem = self.rom
            sim.add_sync_process(wrap(wb_get(dcache, default_mem, "DCACHE")))

        with sim.write_vcd("issuer_simulator.vcd"):
            sim.run()
