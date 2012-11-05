import collections
import inspect

from errors import RequirementError, RequirementAttributeError, DeveloperError, NotFound
from introspection import find_obj

class InstallRequirementError(RequirementError):
    path_desc = "installing"
class InstallRequirementAttributeError(RequirementAttributeError):
    path_desc = "installing"

class AppAdmin(object):
    """
        Object that knows about app.__bookkeeper__
        And how to perform sanity checks and installs on the app
    """
    def __init__(self, app):
        self.app = app

    ########################
    ###   USAGE
    ########################

    def bootstrap(self):
        """
            Make sure the app has a __bookkeeper__ property
            Then make sure everything is sane
            and install anything that must be installed
        """
        if not hasattr(self.app, '__bookkeeper__'):
            raise DeveloperError("The app being bootstrap'd needs to have a __bookkeeper__ property")
        self.sanity_check()
        self.install()

    def sanity_check(self):
        """
            Get the bookkeeper to check any sanity requirements
            And call any check_ functions on the app
        """
        app = self.app

        # Make sure any dynamically created things are sane on this instance
        for info in self.sanity_requirements:
            app.__bookkeeper__.path_check(app, info)

        # And call any check functions we have
        for attr in dir(app):
            if attr.startswith("check_"):
                checker = getattr(app, attr)
                if isinstance(checker, collections.Callable) and getattr(checker, '__checker__', True):
                    checker()

    def install(self):
        """Call the install method on anything that bootstrap says should be installed"""
        app = self.app

        for key, installer, origin in self.installers:
            # Make sure the object exists
            try:
                obj = find_obj(app, installer)
            except NotFound as error:
                raise InstallRequirementError(origin=origin, path=error.path, base=error.base, identity=key, found=error.found)

            # Make sure it has an install method
            if not hasattr(obj, 'install'):
                raise InstallRequirementAttributeError(origin=origin, path=installer, obj=obj, identity=key, requires="install")
            
            # And finally, call the installer
            obj.install(app)

    ########################
    ###   UTILITY
    ########################

    def from_mro(self, key):
        """
            Look through mro for occurances of the key
            Where key is a dot seperated path to something
            so key=components.blah.install
            Will find base.components.blah.install for all the bases in the mro for the app
        """
        installed = {}
        for obj in inspect.getmro(self.app.__class__):
            try:
                yield find_obj(obj, key), obj
            except NotFound:
                pass

    @property
    def installers(self):
        """
            Get all the installers specified by each base in the app's mro.
            Making sure to get the path to each installer
            for only the first occurance of each installer identity
        """
        installed = []
        for installers, base in self.from_mro("_installers"):
            if installers:
                for key, installer in installers.items():
                    if key not in installed and not key.startswith("_"):
                        installed.append(key)
                        if installer is not None:
                            origin = base
                            if hasattr(base, "Install"):
                                origin = base.Install
                            yield key, installer, origin

                # Make sure we ignore inherited things to install if need be
                if not installers.get('__extend__', True):
                    break 

    @property
    def sanity_requirements(self):
        """
            Get __bookkeeper__.requirements for each base in the mro
            Making sure to only get the first requirement for each identity
        """
        found = []
        for requirements, _ in self.from_mro('__bookkeeper__.requirements'):
            if requirements:
                for paths, identity, origin in requirements:
                    if identity not in found:
                        found.append(identity)
                        yield paths, identity, origin
