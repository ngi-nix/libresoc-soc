"""Simple example of a FSM-based ALU

This demonstrates a design that follows the valid/ready protocol of the
ALU, but with a FSM implementation, instead of a pipeline.

The basic rules are:

1) p.ready_o is asserted on the initial ("Idle") state, otherwise it keeps low.
2) n.valid_o is asserted on the final ("Done") state, otherwise it keeps low.
3) The FSM stays in the Idle state while p.valid_i is low, otherwise
   it accepts the input data and moves on.
4) The FSM stays in the Done state while n.ready_i is low, otherwise
   it releases the output data and goes back to the Idle state.
"""
