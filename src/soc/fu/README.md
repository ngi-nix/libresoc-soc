# Pipelines

In this directory are the pipelines.  The structure of each pipeline is
as follows:

* pipe_data.py: contains pipeline input and output data structures
* XXXX_stage.py: files with function-specific stages
* XXX_input_record.py: a PowerISA decoded instruction subset for this pipeline
* pipeline.py: the actual pipeline chain, which brings all stages together

# Computation Units

A subdirectory named compunits contains the 6600 style "Comp Units".
These are pipeline managers whose sole job is to monitor the operation
in its entirety from start to finish, including receiving of all
operands and the storage of all results. AT NO TIME does a Comp Unit
"abandon" data to a pipeline.

Each pipeline is given a Como Umit frontend.  The base class uses regsoecs
to construct the required latches in order to send and receive dsta to
and from the required Register Files.

# Common files

* regspec.py: the register specification API.  used by each pipe_data.py
* pipe_data.py: base class for pipeline pipe_data.py data structures
* common_input_stage.py: functionality common to input stages (RA, RB)
* common_output_stage.py: functionality common to output stages (SO, CA/32 etc.)
