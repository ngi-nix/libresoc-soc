# Verifies the given values are equal
# Arguments:
#   p (Prefix): Appended to the front of the assert statement
#   e (Expected): The expected value
#   o (Output): The output result
#   op (Operation): (0 => ==), (1 => !=)
def assert_eq(p, o, e):
    assert o == e, p + " Output " + str(o) + " Expected " + str(e)
    
# Verifies the given values are not equal
# Arguments:
#   p (Prefix): Appended to the front of the assert statement
#   e (Expected): The expected value
#   o (Output): The output result
def assert_ne(p, o, e):
    assert o != e, p + " Output " + str(o) + " Not Expecting " + str(e) 