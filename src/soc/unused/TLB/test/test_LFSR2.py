# SPDX-License-Identifier: LGPL-2.1-or-later
# See Notices.txt for copyright information
from soc.TLB.LFSR import LFSR, LFSRPolynomial, LFSR_POLY_3

from nmigen.back.pysim import Simulator, Delay, Tick
import unittest


class TestLFSR(unittest.TestCase):
    def test_poly(self):
        v = LFSRPolynomial()
        self.assertEqual(repr(v), "LFSRPolynomial([0])")
        self.assertEqual(str(v), "1")
        v = LFSRPolynomial([1])
        self.assertEqual(repr(v), "LFSRPolynomial([1, 0])")
        self.assertEqual(str(v), "x + 1")
        v = LFSRPolynomial([0, 1])
        self.assertEqual(repr(v), "LFSRPolynomial([1, 0])")
        self.assertEqual(str(v), "x + 1")
        v = LFSRPolynomial([1, 2])
        self.assertEqual(repr(v), "LFSRPolynomial([2, 1, 0])")
        self.assertEqual(str(v), "x^2 + x + 1")
        v = LFSRPolynomial([2])
        self.assertEqual(repr(v), "LFSRPolynomial([2, 0])")
        self.assertEqual(str(v), "x^2 + 1")
        self.assertEqual(str(LFSR_POLY_3), "x^3 + x^2 + 1")

    def test_lfsr_3(self):
        module = LFSR(LFSR_POLY_3)
        traces = [module.state, module.enable]
        with Simulator(module,
                       vcd_file=open("Waveforms/test_LFSR2.vcd", "w"),
                       gtkw_file=open("Waveforms/test_LFSR2.gtkw", "w"),
                       traces=traces) as sim:
            sim.add_clock(1e-6, phase=0.25e-6)
            delay = Delay(1e-7)

            def async_process():
                yield module.enable.eq(0)
                yield Tick()
                self.assertEqual((yield module.state), 0x1)
                yield Tick()
                self.assertEqual((yield module.state), 0x1)
                yield module.enable.eq(1)
                yield Tick()
                yield delay
                self.assertEqual((yield module.state), 0x2)
                yield Tick()
                yield delay
                self.assertEqual((yield module.state), 0x5)
                yield Tick()
                yield delay
                self.assertEqual((yield module.state), 0x3)
                yield Tick()
                yield delay
                self.assertEqual((yield module.state), 0x7)
                yield Tick()
                yield delay
                self.assertEqual((yield module.state), 0x6)
                yield Tick()
                yield delay
                self.assertEqual((yield module.state), 0x4)
                yield Tick()
                yield delay
                self.assertEqual((yield module.state), 0x1)
                yield Tick()

            sim.add_process(async_process)
            sim.run()
