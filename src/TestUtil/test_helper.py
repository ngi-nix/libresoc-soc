def assert_op(pre, o, e, op):
    """ Verifies the given values given the particular operand
        Arguments:
            p (Prefix): Appended to the front of the assert statement
            e (Expected): The expected value
            o (Output): The output result
            op (Operation): (0 => ==), (1 => !=)
    """
    if op == 0:
        assert_eq(pre, o, e)
    else:
        assert_ne(pre, o, e)    

def assert_eq(p, o, e):
    """ Verifies the given values are equal
        Arguments:
           p (Prefix): Appended to the front of the assert statement
           e (Expected): The expected value
           o (Output): The output result
    """
    assert o == e, p + " Output " + str(o) + " Expected " + str(e)
    
def assert_ne(p, o, e):
    """ Verifies the given values are not equal
        Arguments:
           p (Prefix): Appended to the front of the assert statement
           e (Expected): The expected value
           o (Output): The output result
    """
    assert o != e, p + " Output " + str(o) + " Not Expecting " + str(e) 
