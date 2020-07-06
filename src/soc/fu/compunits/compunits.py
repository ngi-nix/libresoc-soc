###################################################################
"""Function Units Construction

This module pulls all of the pipelines together (soc.fu.*) and, using
the regspec and Computation Unit APIs, constructs Scoreboard-aware
Function Units that may systematically and automatically be wired up
to appropriate Register Files.

Two types exist:

* Single-cycle Function Units.  these are FUs that will only block for
  one cycle.  it is expected that multiple of these be instantiated,
  because they are simple and trivial, and not many gates.

  - ALU, Logical: definitely several
  - CR: not so many needed (perhaps)
  - Branch: one or two of these (depending on speculation run-ahead)
  - Trap: yeah really only one of these
  - SPR: again, only one.
  - ShiftRot (perhaps not too many of these)

* Multi-cycle (and FSM) Function Units.  these are FUs that can only
  handle a limited number of values, and take several cycles to complete.
  Given that under Scoreboard Management, start and completion must be
  fully managed, a "Reservation Station" style approach is required:
  *one* multiple-stage (N stage) pipelines need a minimum of N (plural)
  "CompUnit" front-ends.  this includes:

  - MUL (all versions including MAC)
  - DIV (including modulo)

In either case, there will be multiple MultiCompUnits: it's just that
single-cycle ones are instantiated individually (one single-cycle pipeline
per MultiCompUnit, and multi-cycle ones need to be instantiated en-masse,
where *only one* actual pipeline (or FSM) has *multiple* Reservation
Stations.

see:

* https://libre-soc.org/3d_gpu/architecture/regfile/ section on regspecs

"""

# imports

from nmigen import Elaboratable, Module
from nmigen.cli import rtlil
from soc.experiment.compalu_multi import MultiCompUnit
from soc.decoder.power_enums import Function

# pipeline / spec imports

from soc.fu.alu.pipeline import ALUBasePipe
from soc.fu.alu.pipe_data import ALUPipeSpec

from soc.fu.logical.pipeline import LogicalBasePipe
from soc.fu.logical.pipe_data import LogicalPipeSpec

from soc.fu.cr.pipeline import CRBasePipe
from soc.fu.cr.pipe_data import CRPipeSpec

from soc.fu.branch.pipeline import BranchBasePipe
from soc.fu.branch.pipe_data import BranchPipeSpec

from soc.fu.shift_rot.pipeline import ShiftRotBasePipe
from soc.fu.shift_rot.pipe_data import ShiftRotPipeSpec

from soc.fu.spr.pipeline import SPRBasePipe
from soc.fu.spr.pipe_data import SPRPipeSpec

from soc.fu.trap.pipeline import TrapBasePipe
from soc.fu.trap.pipe_data import TrapPipeSpec

from soc.fu.div.pipeline import DIVBasePipe
from soc.fu.div.pipe_data import DIVPipeSpec

from soc.fu.mul.pipeline import MulBasePipe
from soc.fu.mul.pipe_data import MulPipeSpec

from soc.fu.ldst.pipe_data import LDSTPipeSpec
from soc.experiment.compldst_multi import LDSTCompUnit # special-case


###################################################################
###### FunctionUnitBaseSingle - use to make single-stge pipes #####

class FunctionUnitBaseSingle(MultiCompUnit):
    """FunctionUnitBaseSingle

    main "glue" class that brings everything together.
    ONLY use this class for single-stage pipelines.

    * :speckls:  - the specification.  contains regspec and op subset info,
                   and contains common "stuff" like the pipeline ctx,
                   what type of nmutil pipeline base is to be used (etc)
    * :pipekls:  - the type of pipeline.  actually connects things together

    note that it is through MultiCompUnit.get_in/out that we *actually*
    connect up the association between regspec variable names (defined
    in the pipe_data).

    note that the rdflags function obtains (dynamically, from instruction
    decoding) which read-register ports are to be requested.  this is not
    ideal (it could be a lot neater) but works for now.
    """
    def __init__(self, speckls, pipekls, idx):
        alu_name = "alu_%s%d" % (self.fnunit.name.lower(), idx)
        pspec = speckls(id_wid=2)                # spec (NNNPipeSpec instance)
        opsubset = pspec.opsubsetkls             # get the operand subset class
        regspec = pspec.regspec                  # get the regspec
        alu = pipekls(pspec)                     # create actual NNNBasePipe
        super().__init__(regspec, alu, opsubset, name=alu_name) # MultiCompUnit


##############################################################
# TODO: ReservationStations-based (FunctionUnitBaseConcurrent)

class FunctionUnitBaseMulti:
    pass


######################################################################
###### actual Function Units: these are "single" stage pipelines #####

class ALUFunctionUnit(FunctionUnitBaseSingle):
    fnunit = Function.ALU
    def __init__(self, idx):
        super().__init__(ALUPipeSpec, ALUBasePipe, idx)

class LogicalFunctionUnit(FunctionUnitBaseSingle):
    fnunit = Function.LOGICAL
    def __init__(self, idx):
        super().__init__(LogicalPipeSpec, LogicalBasePipe, idx)

class CRFunctionUnit(FunctionUnitBaseSingle):
    fnunit = Function.CR
    def __init__(self, idx):
        super().__init__(CRPipeSpec, CRBasePipe, idx)

class BranchFunctionUnit(FunctionUnitBaseSingle):
    fnunit = Function.BRANCH
    def __init__(self, idx):
        super().__init__(BranchPipeSpec, BranchBasePipe, idx)

class ShiftRotFunctionUnit(FunctionUnitBaseSingle):
    fnunit = Function.SHIFT_ROT
    def __init__(self, idx):
        super().__init__(ShiftRotPipeSpec, ShiftRotBasePipe, idx)

class DIVFunctionUnit(FunctionUnitBaseSingle):
    fnunit = Function.DIV
    def __init__(self, idx):
        super().__init__(DIVPipeSpec, DIVBasePipe, idx)

class MulFunctionUnit(FunctionUnitBaseSingle):
    fnunit = Function.MUL
    def __init__(self, idx):
        super().__init__(MulPipeSpec, MulBasePipe, idx)

class TrapFunctionUnit(FunctionUnitBaseSingle):
    fnunit = Function.TRAP
    def __init__(self, idx):
        super().__init__(TrapPipeSpec, TrapBasePipe, idx)

class SPRFunctionUnit(FunctionUnitBaseSingle):
    fnunit = Function.SPR
    def __init__(self, idx):
        super().__init__(SPRPipeSpec, SPRBasePipe, idx)

# special-case
class LDSTFunctionUnit(LDSTCompUnit):
    fnunit = Function.LDST
    def __init__(self, pi, awid, idx):
        pspec = LDSTPipeSpec(id_wid=2)           # spec (NNNPipeSpec instance)
        opsubset = pspec.opsubsetkls             # get the operand subset class
        regspec = pspec.regspec                  # get the regspec
        super().__init__(pi, regspec, awid, opsubset)


#####################################################################
###### actual Function Units: these are "multi" stage pipelines #####

# TODO: ReservationStations-based.


# simple one-only function unit class, for test purposes
class AllFunctionUnits(Elaboratable):
    """AllFunctionUnits

    creates a dictionary of Function Units according to required spec.
    tuple is of:

     * name of ALU,
     * quantity of FUs required
     * type of FU required

    """
    def __init__(self, pspec, pilist=None):
        addrwid = pspec.addr_wid
        units = pspec.units
        if not isinstance(units, dict):
            units = {'alu': 1, 'cr': 1, 'branch': 1, 'trap': 1,
                     #'spr': 1, TODO: spr regfile
                     'logical': 1,
                     'mul': 1,
                     'div': 1, 'shiftrot': 1}
        alus = {'alu': ALUFunctionUnit,
                 'cr': CRFunctionUnit,
                 'branch': BranchFunctionUnit,
                 'trap': TrapFunctionUnit,
                 'spr': SPRFunctionUnit,
                 'div': DIVFunctionUnit,
                 'mul': MulFunctionUnit,
                 'logical': LogicalFunctionUnit,
                 'shiftrot': ShiftRotFunctionUnit,
                }
        self.fus = {}
        for name, qty in units.items():
            kls = alus[name]
            for i in range(qty):
                self.fus["%s%d" % (name, i)] = kls(i)
        if pilist is None:
            return
        for i, pi in enumerate(pilist):
            self.fus["ldst%d" % (i)] = LDSTFunctionUnit(pi, addrwid, i)

    def elaborate(self, platform):
        m = Module()
        for (name, fu) in self.fus.items():
            setattr(m.submodules, name, fu)
        return m

    def __iter__(self):
        for (name, fu) in self.fus.items():
            yield from fu.ports()

    def ports(self):
        return list(self)


def tst_single_fus_il():
    for (name, kls) in (('alu', ALUFunctionUnit),
                        ('cr', CRFunctionUnit),
                        ('branch', BranchFunctionUnit),
                        ('trap', TrapFunctionUnit),
                        ('spr', SPRFunctionUnit),
                        ('mul', MulFunctionUnit),
                        ('logical', LogicalFunctionUnit),
                        ('shiftrot', ShiftRotFunctionUnit)):
        fu = kls(0)
        vl = rtlil.convert(fu, ports=fu.ports())
        with open("fu_%s.il" % name, "w") as f:
            f.write(vl)


def tst_all_fus():
    dut = AllFunctionUnits()
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("all_fus.il", "w") as f:
        f.write(vl)

if __name__ == '__main__':
    tst_single_fus_il()
    tst_all_fus()
