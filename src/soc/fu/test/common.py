class TestCase:
    def __init__(self, program, name, regs=None, sprs=None, cr=0, mem=None,
                       msr=0):

        self.program = program
        self.name = name

        if regs is None:
            regs = [0] * 32
        if sprs is None:
            sprs = {}
        if mem is None:
            mem = {}
        self.regs = regs
        self.sprs = sprs
        self.cr = cr
        self.mem = mem
        self.msr = msr

class ALUHelpers:

    def set_int_ra(alu, dec2, inp):
        if 'ra' in inp:
            yield alu.p.data_i.ra.eq(inp['ra'])

    def set_int_rb(alu, dec2, inp):
        if 'rb' in inp:
            yield alu.p.data_i.rb.eq(inp['rb'])
        # If there's an immediate, set the B operand to that
        imm_ok = yield dec2.e.imm_data.imm_ok
        if imm_ok:
            data2 = yield dec2.e.imm_data.imm
            yield alu.p.data_i.b.eq(data2)

    def set_xer_ca(alu, dec2, inp):
        if 'xer_ca' in inp:
            yield alu.p.data_i.xer_ca.eq(inp['xer_ca'])
            print ("extra inputs: CA/32", bin(inp['xer_ca']))

    def set_xer_so(alu, dec2, inp):
        if 'xer_so' in inp:
            so = inp['xer_so']
            print ("extra inputs: so", so)
            yield alu.p.data_i.xer_so.eq(so)

    def set_fast_cia(alu, dec2, inp):
        if 'cia' in inp:
            yield alu.p.data_i.cia.eq(inp['cia'])

    def set_fast_spr1(alu, dec2, inp):
        if 'spr1' in inp:
            yield alu.p.data_i.spr1.eq(inp['spr1'])

    def set_fast_spr2(alu, dec2, inp):
        if 'spr2' in inp:
            yield alu.p.data_i.spr2.eq(inp['spr2'])

    def set_cr_a(alu, dec2, inp):
        if 'cr_a' in inp:
            yield alu.p.data_i.cr.eq(inp['cr_a'])

