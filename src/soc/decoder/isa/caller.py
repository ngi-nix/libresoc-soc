from functools import wraps

class ISACaller:
    def __init__(self):
        self.gpr = {} # TODO
        self.mem = {} # TODO
        self.namespace = {'GPR': self.gpr,
                          'MEM': self.mem,
                          'memassign': self.memassign
                         }

    def memassign(self, ea, sz, val):
        pass

def inject(context):
    """ Decorator factory. """
    def variable_injector(func):
        @wraps(func)
        def decorator(*args, **kwargs):
            try:
                func_globals = func.__globals__  # Python 2.6+
            except AttributeError:
                func_globals = func.func_globals  # Earlier versions.

            saved_values = func_globals.copy()  # Shallow copy of dict.
            func_globals.update(context)

            result = func(*args, **kwargs)
            #exec (func.__code__, func_globals)

            #finally:
            #    func_globals = saved_values  # Undo changes.

            return result

        return decorator

    return variable_injector

if __name__ == '__main__':
    d = {'1': 1}
    namespace = {'a': 5, 'b': 3, 'd': d}

    @inject(namespace)
    def test():
        print (globals())
        print('a:', a)
        print('b:', b)
        print('d1:', d['1'])
        d[2] = 5
        
        return locals()

    test()

    print (namespace)
