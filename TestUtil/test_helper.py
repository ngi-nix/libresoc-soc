# Verifies the given values via the requested operation
# Arguments:
#   p (Prefix): Appended to the front of the assert statement
#   e (Expected): The expected value
#   o (Output): The output result
#   op (Operation): (0 => ==), (1 => !=)
def check(p, o, e, op):
    if(op == 0):
        assert o == e, p + " Output " + str(o) + " Expected " + str(e)
    else:
        assert o != e, p + " Output " + str(o) + " Not Expecting " + str(e) 