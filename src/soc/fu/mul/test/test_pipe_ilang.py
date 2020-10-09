import unittest
from nmigen.cli import rtlil
from soc.fu.mul.pipe_data import MulPipeSpec
from soc.fu.mul.pipeline import MulBasePipe


class TestPipeIlang(unittest.TestCase):
    def write_ilang(self):
        pspec = MulPipeSpec(id_wid=2)
        alu = MulBasePipe(pspec)
        vl = rtlil.convert(alu, ports=alu.ports())
        with open("mul_pipeline.il", "w") as f:
            f.write(vl)

    def test_ilang(self):
        self.write_ilang()


if __name__ == "__main__":
    unittest.main()
