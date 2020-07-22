from nmutil.singlepipe import ControlBase
from nmutil.pipemodbase import PipeModBaseChain
from soc.fu.mul.output_stage import DivMulOutputStage
from soc.fu.div.input_stage import DivMulInputStage
from soc.fu.div.output_stage import DivOutputStage
from soc.fu.div.setup_stage import DivSetupStage
from soc.fu.div.core_stages import (DivCoreSetupStage, DivCoreCalculateStage,
                                    DivCoreFinalStage)
from soc.fu.div.pipe_data import DivPipeKindConfigCombPipe


class DivStagesStart(PipeModBaseChain):
    def get_chain(self):
        alu_input = DivMulInputStage(self.pspec)
        div_setup = DivSetupStage(self.pspec)
        if isinstance(self.pspec.div_pipe_kind.config,
                      DivPipeKindConfigCombPipe):
            core_setup = [DivCoreSetupStage(self.pspec)]
        else:
            core_setup = ()
        return [alu_input, div_setup, *core_setup]


class DivStagesMiddle(PipeModBaseChain):
    def __init__(self, pspec, stage_start_index, stage_end_index):
        assert isinstance(pspec.div_pipe_kind.config,
                          DivPipeKindConfigCombPipe),\
            "DivStagesMiddle must be used with a DivPipeKindConfigCombPipe"
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
        if isinstance(self.pspec.div_pipe_kind.config,
                      DivPipeKindConfigCombPipe):
            core_final = [DivCoreFinalStage(self.pspec)]
        else:
            core_final = ()
        div_out = DivOutputStage(self.pspec)
        alu_out = DivMulOutputStage(self.pspec)
        self.div_out = div_out  # debugging - bug #425
        return [*core_final, div_out, alu_out]


class DivBasePipe(ControlBase):
    def __init__(self, pspec, compute_steps_per_stage=4):
        ControlBase.__init__(self)
        self.pspec = pspec
        self.pipe_start = DivStagesStart(pspec)
        self.pipe_middles = []
        if isinstance(self.pspec.div_pipe_kind.config,
                      DivPipeKindConfigCombPipe):
            compute_steps = pspec.core_config.n_stages
            for start in range(0, compute_steps, compute_steps_per_stage):
                end = min(start + compute_steps_per_stage, compute_steps)
                self.pipe_middles.append(DivStagesMiddle(pspec, start, end))
        else:
            self.pipe_middles.append(
                self.pspec.div_pipe_kind.config.core_stage_class(pspec))
        self.pipe_end = DivStagesEnd(pspec)
        self._eqs = self.connect([self.pipe_start,
                                  *self.pipe_middles,
                                  self.pipe_end])

    def elaborate(self, platform):
        m = ControlBase.elaborate(self, platform)
        m.submodules.pipe_start = self.pipe_start
        for i in range(len(self.pipe_middles)):
            name = f"pipe_middle_{i}"
            setattr(m.submodules, name, self.pipe_middles[i])
        m.submodules.pipe_end = self.pipe_end
        m.d.comb += self._eqs
        return m
