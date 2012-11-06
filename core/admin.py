import collections
import inspect

from errors import RequirementError, RequirementAttributeError, DeveloperError, NotFound
from introspection import find_obj, iterate_bookkeepers, position_for

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
        self.app_kls = app.__class__

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
        self.create_things()
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

        # Make sure our methods point to callables
        found = []
        for methods, _ in iterate_bookkeepers(self.app_kls, 'methods'):
            for identity in methods:
                if identity not in found:
                    found.append(identity)
                    current = getattr(self.app, identity, None)
                    if not isinstance(current, collections.Callable):
                        raise self.app.__bookkeeper__.UnexpectedValueError(identity, self.app, "Expected to be a callable")

    def install(self):
        """Call the install method on anything that bootstrap says should be installed"""
        app = self.app

        for key, installer, origin in self.installers:
            # Make sure the object exists
            try:
                obj = find_obj(app, installer)
            except NotFound as error:
                error_args = dict(origin=origin, path=error.path, base=error.base, identity=key, found=error.found)
                error_args.update(self.app.__bookkeeper__.paper_trail(installer, app))
                raise InstallRequirementError(**error_args)

            # Make sure it has an install method
            if not hasattr(obj, 'install'):
                raise InstallRequirementAttributeError(origin=origin, path=installer, obj=obj, identity=key, requires="install")

            # And finally, call the installer
            obj.install(app)

    def create_things(self):
        """Get things from the bookkeeper that should be put onto the app"""
        created = []
        for creator, _ in iterate_bookkeepers(self.app_kls, 'create_objects'):
            for attribute, value in creator():
                if attribute not in created:
                    created.append(attribute)
                    setattr(self.app, attribute, value)

    ########################
    ###   UTILITY
    ########################

    @property
    def installers(self):
        """
            Get all the installers specified by each base in the app's mro.
            Making sure to get the path to each installer
            for only the first occurance of each installer identity
        """
        installed = []
        for installers, base in iterate_bookkeepers(self.app_kls, "installers"):
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
        for requirements, _ in iterate_bookkeepers(self.app_kls, "requirements"):
            if requirements:
                for paths, identity, origin in requirements:
                    if identity not in found:
                        found.append(identity)
                        yield paths, identity, origin
