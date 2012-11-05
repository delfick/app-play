import inspect
import os

from errors import NotFound

def whereami():
    """Get source file and line number for place where this function is called"""
    source, line = inspect.stack()[-2][1:3]
    return (os.path.abspath(source), line)

def location_of(thing):
    """Determine the source file and line number for the object passed in"""
    if hasattr(thing, '__location__'):
        location, number = thing.__location__
    else:
        number = None
        location = None
        try:
            location = os.path.abspath(inspect.getsourcefile(thing))
        except TypeError:
            # Must have been a builtin
            pass

        if location is not None:
            try:
                _, number = inspect.getsourcelines(thing)
            except IOError:
                # Couldn't read source file
                pass
    return location, number

def position_for(thing):
    """Get a human readable string for location and filenumber of thing passed in"""
    if thing is None:
        return "Unknown"

    location, number = location_of(thing)
    if location is None:
        return repr(thing)

    base = "{} at {}".format(repr(thing), location)
    if number is None:
        return base
    else:
        return "{}:{}".format(base, number)

def find_obj(base, path):
    """
        Find and return attribute at base.<path>
        where path is a dot seperated path to some attribute
        Raise NotFound if can't find the attribute
    """
    obj = base
    found = []
    parts = path.split(".")

    for part in parts:
        if not hasattr(obj, part):
            raise NotFound(path=path, base=base, found=found)
        obj = getattr(obj, part)
        found.append(part)
    return obj
