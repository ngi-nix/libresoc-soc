"""simple core issuer verilog generator
"""

import sys
from nmigen.cli import verilog

from soc.config.test.test_loadstore import TestMemPspec
from soc.simple.issuer import TestIssuer


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

    vl = verilog.convert(dut, ports=dut.ports(), name="test_issuer")
    with open(sys.argv[1], "w") as f:
        f.write(vl)
