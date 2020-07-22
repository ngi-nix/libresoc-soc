from pygdbmi.gdbcontroller import GdbController
import subprocess

launch_args_be = ['qemu-system-ppc64',
                  '-machine', 'powernv9',
                  '-nographic',
                  '-s', '-S']

launch_args_le = ['qemu-system-ppc64le',
                  '-machine', 'powernv9',
                  '-nographic',
                  '-s', '-S']


def swap_order(x, nbytes):
    x = x.to_bytes(nbytes, byteorder='little')
    x = int.from_bytes(x, byteorder='big', signed=False)
    return x


class QemuController:
    def __init__(self, kernel, bigendian):
        if bigendian:
            args = launch_args_be + ['-kernel', kernel]
        else:
            args = launch_args_le + ['-kernel', kernel]
        self.qemu_popen = subprocess.Popen(args,
                                           stdout=subprocess.PIPE,
                                           stdin=subprocess.PIPE)
        self.gdb = GdbController(gdb_path='powerpc64-linux-gnu-gdb')
        self.bigendian = bigendian

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.exit()

    def connect(self):
        return self.gdb.write('-target-select remote localhost:1234')

    def set_endian(self, bigendian):
        if bigendian:
            cmd = '-gdb-set endian big'
        else:
            cmd = '-gdb-set endian little'
        return self.gdb.write(cmd)

    def break_address(self, addr):
        cmd = '-break-insert *0x{:x}'.format(addr)
        return self.gdb.write(cmd)

    def delete_breakpoint(self, breakpoint=None):
        breakstring = ''
        if breakpoint:
            breakstring = f' {breakpoint}'
        return self.gdb.write('-break-delete' + breakstring)

    def set_byte(self, addr, v):
        print("qemu set byte", hex(addr), hex(v))
        faddr = '&{int}0x%x' % addr
        res = self.gdb.write('-data-write-memory-bytes %s "%02x"' % (faddr, v))
        print("confirm", self.get_mem(addr, 1))

    def get_mem(self, addr, nbytes):
        res = self.gdb.write("-data-read-memory %d u 1 1 %d" %
                             (addr, 8*nbytes))
        #print ("get_mem", res)
        for x in res:
            if(x["type"] == "result"):
                l = list(map(int, x['payload']['memory'][0]['data']))
                res = []
                for j in range(0, len(l), 8):
                    b = 0
                    for i, v in enumerate(l[j:j+8]):
                        b += v << (i*8)
                    res.append(b)
                return res
        return None

    def get_registers(self):
        return self.gdb.write('-data-list-register-values x')

    def _get_register(self, fmt):
        res = self.gdb.write('-data-list-register-values '+fmt,
                             timeout_sec=1.0)  # increase this timeout if needed
        for x in res:
            if(x["type"] == "result"):
                assert 'register-values' in x['payload']
                res = int(x['payload']['register-values'][0]['value'], 0)
                return res
                # return swap_order(res, 8)
        return None

    # TODO: use -data-list-register-names instead of hardcoding the values
    def get_pc(self): return self._get_register('x 64')
    def get_msr(self): return self._get_register('x 65')
    def get_cr(self): return self._get_register('x 66')
    def get_lr(self): return self._get_register('x 67')
    def get_ctr(self): return self._get_register('x 68')  # probably
    def get_xer(self): return self._get_register('x 69')
    def get_fpscr(self): return self._get_register('x 70')
    def get_mq(self): return self._get_register('x 71')

    def get_register(self, num):
        return self._get_register('x {}'.format(num))

    def step(self):
        return self.gdb.write('-exec-next-instruction')

    def gdb_continue(self):
        return self.gdb.write('-exec-continue')

    def gdb_eval(self, expr):
        return self.gdb.write(f'-data-evaluate-expression {expr}')

    def exit(self):
        self.gdb.exit()
        self.qemu_popen.kill()
        outs, errs = self.qemu_popen.communicate()
        self.qemu_popen.stdout.close()
        self.qemu_popen.stdin.close()


def run_program(program, initial_mem=None, extra_break_addr=None,
                bigendian=False):
    q = QemuController(program.binfile.name, bigendian)
    q.connect()
    q.set_endian(True)  # easier to set variables this way

    # Run to the start of the program
    if initial_mem:
        for addr, (v, wid) in initial_mem.items():
            for i in range(wid):
                q.set_byte(addr+i, (v >> i*8) & 0xff)

    # set breakpoint at start
    q.break_address(0x20000000)
    q.gdb_continue()
    # set the MSR bit 63, to set bigendian/littleendian mode
    msr = q.get_msr()
    print("msr", bigendian, hex(msr))
    if bigendian:
        msr &= ~(1 << 0)
        msr = msr & ((1 << 64)-1)
    else:
        msr |= (1 << 0)
    q.gdb_eval('$msr=%d' % msr)
    print("msr set to", hex(msr))
    # set the CR to 0, matching the simulator
    q.gdb_eval('$cr=0')
    # delete the previous breakpoint so loops don't screw things up
    q.delete_breakpoint()
    # run to completion
    q.break_address(0x20000000 + program.size())
    # or to trap
    q.break_address(0x700)
    # or to alternative (absolute) address)
    if extra_break_addr:
        q.break_address(extra_break_addr)
    q.gdb_continue()
    q.set_endian(bigendian)

    return q


if __name__ == '__main__':
    q = QemuController("simulator/qemu_test/kernel.bin", bigendian=True)
    q.connect()
    q.break_address(0x20000000)
    q.gdb_continue()
    print(q.get_register(1))
    print(q.step())
    print(q.get_register(1))
    q.exit()
