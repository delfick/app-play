from textwrap import dedent
import inspect

from errors import RequirementError, NotFound, DeveloperError
from introspection import find_obj, position_for, from_mro

class BookKeeper(object):
    """
        Object for keeping track of what is defined on an app
    """
    def __init__(self):
        self.added = {}
        self.removed = {}
        self.replaced = {}

        self.attrs = {}
        self.custom = {}
        self.components = {}
        self.installers = {}
        self.requirements = []

    def update(self, updating, attributes, inherited, extend=True, origin=None, prefix=None):
        """Update one of the dictionaries"""
        if prefix:
            inherited = {"{}.{}".format(prefix, key):None for key in inherited}
            attributes = {"{}.{}".format(prefix, key):val for key, val in attributes.items()}

        if not extend:
            self.removed_attributes(inherited.keys(), origin)

        conflict = set(updating.keys()) - set(attributes.keys())
        if conflict:
            raise DevelopeError("Adding variable already added by the metaclass somewhere", origin=origin)

    def add_requirement(self, paths, identity, origin):
        """
            Add a requirement
            identity requires all the things in paths to be installed
            and was defined by origin
        """
        if isinstance(paths, basestring):
            paths = [paths]
        self.requirements.append((paths, identity, origin))

    def add_attrs(self, attrs, inherited, extend=True, origin=None):
        """Record attributes to add when bootstrapping the instance"""
        self.added_attributes(attrs.keys(), origin)
        self.update(self.attrs, attrs, inherited, extend=extend, origin=origin)
        self.attrs.update(attrs)

    def add_installers(self, installers, inherited, extend=True, origin=None):
        """Record things that require to be installed"""
        if self.installers:
            raise DevelopeError("Adding Installers, but already have some", origin=origin)
        self.update(self.installers, installers, inherited, extend=extend, origin=origin)
        self.installers.update(installers)

    def add_components(self, components, inherited, extend=True, origin=None):
        """Record components"""
        self.added_attributes(["{}.{}".format("components", identity) for identity in components], origin)
        self.update(self.components, components, inherited, extend=extend, origin=origin, prefix="components")

        values = {}
        if extend:
            values.update(inherited)
        values.update(components)

        for identity, kls in values.items():
            self.components["{}.{}".format("components", identity)] = ((identity, kls, {}), origin)

    def add_custom(self, objects, origin=None):
        """Record a custom object"""
        self.added_attributes(objects.keys(), origin)
        for identity, info in objects.items():
            if identity in self.custom:
                raise DevelopeError("Bookkeeper already has a custom class for {}".format(identity), origin=origin)
            self.custom[identity] = (info, origin)

    def added_attributes(self, attributes, origin):
        """Record added attributes"""
        if origin not in self.added:
            self.added[origin] = []
        conflicts = set(self.added[origin]) - set(attributes)
        if conflicts:
            raise DevelopeError("Adding variable already added by the metaclass somewhere", origin=origin)
        self.added[origin].extend(attributes)

    def removed_attributes(self, attributes, origin):
        """Record removed attributes"""
        if origin not in self.removed:
            self.removed[origin] = []
        self.removed[origin].extend(attributes)

    def replaced_attributes(self, attributes, origin):
        """Record replaced attributes"""
        if origin not in self.replaced:
            self.replaced[origin] = []
        self.replaced[origin].extend(attributes)

    def normalise_attr_record(self):
        """Remove spurious added attrs that are actually removed or replaced"""
        for origin, attrs in self.added.items():
            not_added = []

            for attr in attrs:
                if origin in self.removed and attr in self.removed[origin]:
                    not_added.append(attr)

                if origin in self.replaced and attr in self.replaced[origin]:
                    not_added.append(attr)

            if not_added:
                self.added[origin] = [key for key in self.added[origin] if key not in not_added]

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

    def create_objects(self):
        """Yield (attribute, value) for things that should be created"""
        for identity, (info, origin) in self.custom.items():
            yield identity, self.generate_thing(info, origin)

        component_objs = {}
        for identity, (info, origin) in self.components.items():
            name, kls, kwargs = info
            if type(kls) is type:
                component_objs[name] = self.generate_thing(info, origin)
            else:
                component_objs[name] = kls
        yield 'components', type("components", (object, ), component_objs)()

        for identity, val in self.attrs.items():
            if isinstance(val, types.LambdaType) and val.__name__ == '<lambda>':
                val = val()
            yield identity, val

    def generate_thing(self, info, origin):
        """Create an object from a single spec"""
        name, kls, kwargs = info
        if not kls:
            raise DeveloperError("Component {} needs to have a __main__ variable".format(name), origin=origin)

        for key, val in kwargs.items():
            if isinstance(val, types.LambdaType) and val.__name__ == '<lambda>':
                kwargs[key] = val()

        try:
            return kls(**kwargs)
        except Exception as error:
            import traceback
            error = "\n{}".format('\n'.join("\t{}".format(line) for line in dedent(traceback.format_exc()).split('\n')))
            raise DeveloperError("Failed to create custom object '{}'.".format(name)
                , error = error
                , origin = origin
                , calling = position_for(kls.__init__)
                , calling_with = kwargs
                , callee_signature = inspect.getargspec(kls.__init__)
                )

    def find_adder(self, identity, base):
        """Determine what in the mro added this particular attribute"""
        bookkeeper = getattr(base, '__bookkeeper__', None)
        if bookkeeper:
            added = {}
            for origin, keys in bookkeeper.added.items():
                for key in keys:
                    added[key] = origin

            replaced = {}
            for origin, keys in bookkeeper.replaced.items():
                for key in keys:
                    replaced[key] = origin

            if identity in added:
                return added[identity]
            if identity in replaced:
                return replaced[identity]

        if identity in base.__dict__:
            return base

        for parent in from_mro(base.__class__, not_self=True):
            found = self.find_adder(identity, parent)
            if found:
                return found

    def find_remover(self, identity, base):
        """Determine what in the mro added this particular attribute"""
        bookkeeper = getattr(base, '__bookkeeper__', None)
        if bookkeeper:
            removed = {}
            for origin, keys in bookkeeper.removed.items():
                for key in keys:
                    removed[key] = origin

            if identity in removed:
                return removed[identity]

        for parent in from_mro(base.__class__, not_self=True):
            found = self.find_remover(identity, parent)
            if found:
                return found
