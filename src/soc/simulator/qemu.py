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

    def connect(self):
        return self.gdb.write('-target-select remote localhost:1234')

    def break_address(self, addr):
        cmd = '-break-insert *0x{:x}'.format(addr)
        return self.gdb.write(cmd)

    def get_registers(self):
        return self.gdb.write('-data-list-register-values x')

    def get_register(self, num):
        return self.gdb.write('-data-list-register-values x {}'.format(num))

    def step(self):
        return self.gdb.write('-exec-next-instruction')

    def gdb_continue(self):
        return self.gdb.write('-exec-continue')
        
    def exit(self):
        self.gdb.exit()
        self.qemu_popen.kill()
                                 

if __name__ == '__main__':
    q = QemuController("qemu_test/kernel.bin")
    q.connect()
    q.break_address(0x20000000)
    q.gdb_continue()
    print(q.get_register(1))
    print(q.step())
    print(q.get_register(1))
    q.exit()

    
