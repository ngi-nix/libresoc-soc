from pygdbmi.gdbcontroller import GdbController
import subprocess

launch_args = ['qemu-system-ppc64',
               '-machine', 'powernv9',
               '-nographic',
               '-s', '-S']


class QemuController:
    def __init__(self, kernel):
        args = launch_args + ['-kernel', kernel]
        self.qemu_popen = subprocess.Popen(args,
                                           stdout=subprocess.PIPE,
                                           stdin=subprocess.PIPE)
        self.gdb = GdbController(gdb_path='powerpc64-linux-gnu-gdb')

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.exit()

    def connect(self):
        return self.gdb.write('-target-select remote localhost:1234')

    def break_address(self, addr):
        cmd = '-break-insert *0x{:x}'.format(addr)
        return self.gdb.write(cmd)

    def get_registers(self):
        return self.gdb.write('-data-list-register-values x')

    def get_register(self, num):
        res = self.gdb.write('-data-list-register-values x {}'.format(num),timeout_sec=1.0) # increase this timeout if needed
        for x in res:
            if(x["type"]=="result"):
                assert 'register-values' in x['payload']
                return int(x['payload']['register-values'][0]['value'], 0)
        return None

    def step(self):
        return self.gdb.write('-exec-next-instruction')

    def gdb_continue(self):
        return self.gdb.write('-exec-continue')

    def exit(self):
        self.gdb.exit()
        self.qemu_popen.kill()
        outs, errs = self.qemu_popen.communicate()
        self.qemu_popen.stdout.close()
        self.qemu_popen.stdin.close()


def run_program(program):
    q = QemuController(program.binfile.name)
    q.connect()
    q.break_address(0x20000000 + program.size())
    q.gdb_continue()
    return q


if __name__ == '__main__':
    q = QemuController("qemu_test/kernel.bin")
    q.connect()
    q.break_address(0x20000000)
    q.gdb_continue()
    print(q.get_register(1))
    print(q.step())
    print(q.get_register(1))
    q.exit()
