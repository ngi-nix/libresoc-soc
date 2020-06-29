from nmutil.singlepipe import ControlBase
from nmutil.pipemodbase import PipeModBaseChain
from soc.fu.alu.input_stage import ALUInputStage
from soc.fu.alu.output_stage import ALUOutputStage
from soc.fu.div.setup_stage import DivSetupStage
from soc.fu.div.core_stages import (DivCoreSetupStage, DivCoreCalculateStage,
                                    DivCoreFinalStage)
from soc.fu.div.output_stage import DivOutputStage


class DivStagesStart(PipeModBaseChain):
    def get_chain(self):
        alu_input = ALUInputStage(self.pspec)
        div_setup = DivSetupStage(self.pspec)
        core_setup = DivCoreSetupStage(self.pspec)
        return [alu_input, div_setup, core_setup]


class DivStagesMiddle(PipeModBaseChain):
    def __init__(self, pspec, stage_start_index, stage_end_index):
        self.stage_start_index = stage_start_index
        self.stage_end_index = stage_end_index
        super().__init__(pspec)

    def get_chain(self):
        stages = []
        for index in range(self.stage_start_index, self.stage_end_index):
            stages.append(DivCoreCalculateStage(self.pspec, index))
        return stages


class DivStagesEnd(PipeModBaseChain):
    def get_chain(self):
        core_final = DivCoreFinalStage(self.pspec)
        div_out = DivOutputStage(self.pspec)
        alu_out = ALUOutputStage(self.pspec)
        return [core_final, div_out, alu_out]


class DIVBasePipe(ControlBase):
    def __init__(self, pspec, compute_steps_per_stage=2):
        ControlBase.__init__(self)
        self.pipe_start = DivStagesStart(pspec)
        compute_steps = pspec.core_config.n_stages
        self.pipe_middles = []
        for start in range(0, compute_steps, compute_steps_per_stage):
            end = min(start + compute_steps_per_stage, compute_steps)
            self.pipe_middles.append(DivStagesMiddle(pspec, start, end))
        self.pipe_end = DivStagesEnd(pspec)
        self._eqs = self.connect([self.pipe_start,
                                  *self.pipe_middles,
                                  self.pipe_end])

    def elaborate(self, platform):
        m = ControlBase.elaborate(self, platform)
        m.submodules.pipe_start = self.pipe_start
        for i in self.pipe_middles:
            name = f"pipe_{i.stage_start_index}_to_{i.stage_end_index}"
            setattr(m.submodules, name, i)
        m.submodules.pipe_end = self.pipe_end
        m.d.comb += self._eqs
        return m
