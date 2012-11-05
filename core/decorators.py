from functools import wraps
from textwrap import dedent

from introspection import find_obj, position_for
from errors import NotFound, RequirementError

def not_extendable(f):
    """Mark a function as not supporting __extend__"""
    f.__extendable__ = False
    return f

def not_nullable(f):
    """Mark a function as not supporting __nullify__"""
    f.__nullable__ = False
    return f

class Uses(object):
    """
        Mark a function as requiring certain attributes on self
        And have those attributes passed into the function when called
        Raise detailed exceptions when those objects can't be found
    """
    def __init__(self, *paths):
        self.paths = paths

    def __call__(self, func):
        @wraps(func)
        def wrapped(app, *args, **kwargs):
            objs = []
            for path in self.paths:
                try:
                    nxt = find_obj(app, path)
                except NotFound as error:
                    raise RequirementError(origin=func, path=error.path, base=error.base, found=error.found)
                objs.append(nxt)
            positional = list(objs) + list(args)
            return func(app, *positional, **kwargs)
        return wrapped
