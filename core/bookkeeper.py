from textwrap import dedent

from errors import RequirementError, NotFound
from introspection import find_obj

class BookKeeper(object):
    """
        Object for keeping track of what is defined on an app
    """
    def __init__(self):
        self.requirements = []

    def add_requirement(self, paths, identity, origin):
        """
            Add a requirement
            identity requires all the things in paths to be installed
            and was defined by origin
        """
        if isinstance(paths, basestring):
            paths = [paths]
        self.requirements.append((paths, identity, origin))

    def path_check(self, app, info):
        """
            Make sure that the app has all the paths specified by paths
            Use identity and origin in the error message if path couldn't ve found
        """
        paths, identity, origin = info
        for path in paths:
            try:
                find_obj(app, path)
            except NotFound as error:
                raise RequirementError(origin=origin, path=error.path, base=error.base, identity=identity, found=error.found)
