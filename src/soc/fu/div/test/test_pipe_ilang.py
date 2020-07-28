import unittest
from nmigen.cli import rtlil
from soc.fu.div.pipe_data import DivPipeSpec, DivPipeKind
from soc.fu.div.pipeline import DivBasePipe


class TestPipeIlang(unittest.TestCase):
    def write_ilang(self, div_pipe_kind):
        pspec = DivPipeSpec(id_wid=2, div_pipe_kind=div_pipe_kind)
        alu = DivBasePipe(pspec)
        vl = rtlil.convert(alu, ports=alu.ports())
        with open(f"div_pipeline_{div_pipe_kind.name}.il", "w") as f:
            f.write(vl)

    def test_div_pipe_core(self):
        self.write_ilang(DivPipeKind.DivPipeCore)

    def test_fsm_div_core(self):
        self.write_ilang(DivPipeKind.FSMDivCore)

    def test_sim_only(self):
        self.write_ilang(DivPipeKind.SimOnly)


if __name__ == "__main__":
    unittest.main()
