# Pipelines

In this directory are the pipelines.  The structure of each pipeline is
as follows:

* pipe_data.py: contains pipeline input and output data structures
* XXXX_stage.py: function-specific stages (connected up together by pipeline.py)
* XXX_input_record.py: a PowerISA decoded instruction subset for this pipeline
* pipeline.py: the actual pipeline chain, which brings all stages together

# Computation Units

A subdirectory named compunits contains the 6600 style "Comp Units".
These are pipeline managers whose sole job is to monitor the operation
in its entirety from start to finish, including receiving of all
operands and the storage of all results. AT NO TIME does a Comp Unit
"abandon" data to a pipeline.

Each pipeline is given a Comp Unit frontend.  The base class uses regspecs
to construct the required latches in order to capture data pending send and
receive data to and from the required Register Files.

# Common files

* regspec.py: the register specification API.  used by each pipe_data.py
* pipe_data.py: base class for pipeline pipe_data.py data structures
* common_input_stage.py: functionality common to input stages (RA, RB)
* common_output_stage.py: functionality common to output stages (SO, CA/32 etc.)

## `pipe_data.py`

### `CommonPipeSpec`

`CommonPipeSpec` creates a specification object that allows convenient
plugging in to the Pipeline API.  In the parallel version this will
involve mix-in using the ReservationStation class.  Construction of
an actual pipeline specification is done, e.g. in `soc.spr.pipe_data`:

    class SPRPipeSpec(CommonPipeSpec):
        regspec = (SPRInputData.regspec, SPROutputData.regspec)
        opsubsetkls = CompSPROpSubset

* **pipekls** defines what type of pipeline base class (dynamic mixin)
is to be used for *ALL* pipelines.  replace with `MaskCancellableRedir`
when the Dependency Matrices are added: mask and stop signals will
then "magically" appear right the way through every single pipeline
(no further effort or coding required as far as the pipelines are concerned).

* **id_wid** is for the `ReservationStation` muxid width.  the muxid
  itself keeps track of which `ReservationStation` the partial results
  are associated with, so that when finally produced the result can be
  put back into the correctly-numbered Reservation Station "bucket".

* **opkls** is the "operation context" which is passed through all pipeline
  stages.  it is a PowerDecoder2 subset (actually Decode2ToOperand)

### `IntegerData`

`IntegerData` is the base class for all pipeline data structures,
providing the "convenience" of auto-construction of members
according to "regspec" definitions. This is conceptually similar to
nmigen Record (Layout, actually) except that Layout does not contain
the right type of information for connecting up to Register Files.

By having a base class that handles creation of pipeline input/output
in a structured fashion, CompUnits may conform to that same structured
API, and when it comes to actually connecting up to regfiles, the same
holds true.  The alternative is mountains of explicit code (which quickly
becomes unmaintainable).

Note the mode parameter - output.  output pipeline data structures need to
have an "ok" flag added (using the Data Record), which is used by the
CompUnit and by the Register File to determine if the output shall in fact be
written to the register file or not.

Input data has *already* been determined to have had to have been read,
this by PowerDecoder2, so does not need any such flag, and consequently
can be a plain "Signal".

Therefore it is critical to note that there has to be properly coordinated
collaboration between `PowerDecoder2` and each pipeline, to ensure that the
inputs set up by `PowerDecoder2` are used *by* the pipeline (on a per
operation basis) *and* that likewise when the pipeline sets up its
outputs, `PowerDecoder2` is aware precisely and exactly where that data
is to be written.  See `DecodeOut`, `OP_RFID` case statement for example.

