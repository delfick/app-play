from textwrap import dedent
import logging
import inspect
import types

from errors import RequirementError, NotFound, DeveloperError, UnexpectedValueError
from introspection import find_obj, position_for, from_mro

class Unknown(object): pass

class BookKeeper(object):
    """
        Object for keeping track of what is defined on an app
    """
    def __init__(self, name):
        self.name = name

        self.added = {}
        self.values = {}
        self.removed = {}
        self.replaced = {}

        self.attrs = {}
        self.custom = {}
        self.methods = {}
        self.checkers = {}
        self.components = {}
        self.installers = {}
        self.requirements = []

        self.log = logging.getLogger("{}:BookKeeper".format(name))

    def value_for(self, identity, origin):
        """Attempt to guess a value for some attribute given it's origin"""
        if not hasattr(origin, '__name__'):
            return Unknown

        name = origin.__name__.lower()
        values = getattr(self, name, None)
        if not values or identity not in values:
            return Unknown

        return values[identity]

    def debug(self, msg, **kwargs):
        origin = kwargs.get('origin')
        if 'origin' in kwargs:
            del kwargs['origin']
        origin = "{}:{}({})".format(self.name, origin.__name__, position_for(origin, with_repr=False))

        template = "\t".join("{}=%s".format(key) for key in sorted(kwargs.keys()))
        values = [msg, origin] + [v for _, v in sorted(kwargs.items())]
        self.log.debug("%s\torigin=%s\t{}".format(template), *values)

    def UnexpectedValueError(self, identity, app, msg=None):
        """Return an exception that can be raised to announce an unexpected value"""
        if msg is None:
            msg = "Unexpected value"

        error_args = dict(identity=identity, app=app)
        error_args.update(self.paper_trail(identity, app))
        return UnexpectedValueError(msg, **error_args)

    def paper_trail(self, identity, app):
        """Return where something is added and removed by"""
        added_by = self.find_adder(identity, app)
        removed_by = self.find_remover(identity, app)
        return dict(added_by=added_by, removed_by=removed_by)

    @property
    def added_keys(self):
        keys = []
        for origin, attrs in self.added.items():
            keys.extend(attrs)
        return attrs

    @property
    def removed_keys(self):
        keys = []
        for origin, attrs in self.removed.items():
            keys.extend(attrs)
        return attrs

    @property
    def replaced_keys(self):
        keys = []
        for origin, attrs in self.replaced.items():
            keys.extend(attrs)
        return attrs

    def update(self, updating, attributes, inherited
        , extend=True, origin=None, prefix=None, everything_once_only=False, each_once_only=False, manually_update=False, store_with_origin=False):
        """Update one of the dictionaries"""
        if not attributes:
            return {}

        if not inherited:
            inherited = {}

        if any(key.startswith("_") for key in attributes):
            attributes = {key:val for key, val in attributes.items() if not key.startswith("_")}

        if any(key.startswith("_") for key in inherited):
            inherited = {key:val for key, val in inherited.items() if not key.startswith("_")}

        debug_kwargs = {updating:attributes.keys(), 'origin':origin}
        self.debug("Adding {}".format(updating), **debug_kwargs)

        values = getattr(self, updating)
        if everything_once_only and values:
            raise DevelopeError("Adding '{}', but already have some".format(updating), origin=origin)

        if prefix:
            inherited = {"{}.{}".format(prefix, key):val for key, val in inherited.items()}
            attributes = {"{}.{}".format(prefix, key):val for key, val in attributes.items()}

        if each_once_only:
            for key in attributes:
                if key in values:
                    raise DeveloperError("There can only be one {} with identity {}".format(updating, key), origin=origin)

        added = [key for key in attributes if attributes[key] is not None]
        removed = [key for key in attributes if attributes[key] is None]
        if not extend:
            removed.extend(key for key in inherited.keys() if key not in added and key not in removed)

        conflict = set(attributes.keys()) - (set(attributes.keys()) - set(values.keys()))
        if conflict:
            raise DeveloperError("Adding same variables ({}) to '{}' even though this bookkeeper has already added that".format(list(conflict), updating), origin=origin)

        self.added_attributes(added, origin)
        self.removed_attributes(removed, origin)

        adding = attributes
        if extend:
            adding = {}
            adding.update(inherited)
            adding.update(attributes)

        if not manually_update:
            if store_with_origin:
                values.update({key:(val, origin) for key, val in adding.items()})
            else:
                values.update(adding)
        return adding

    def add_requirement(self, paths, identity, origin):
        """
            Add a requirement
            identity requires all the things in paths to be installed
            and was defined by origin
        """
        if not paths:
            return

        if isinstance(paths, basestring):
            paths = [paths]

        self.debug("Adding requirements", identity=identity, paths=paths)
        self.requirements.append((paths, identity, origin))

    def add_attrs(self, attrs, inherited, extend=True, origin=None):
        """Record attributes to add when bootstrapping the instance"""
        self.update("attrs", attrs, inherited, extend=extend, origin=origin)

    def add_methods(self, methods, inherited, extend=True, origin=None):
        """Record methods that were added"""
        self.update("methods", methods, inherited, extend=extend, origin=origin)

    def add_checkers(self, checkers, inherited, extend=True, origin=None):
        """Record checker methods that were added"""
        self.update("checkers", checkers, inherited, extend=extend, origin=origin)

    def add_installers(self, installers, inherited, extend=True, origin=None):
        """Record things that require to be installed"""
        self.update('installers', installers, inherited, extend=extend, origin=origin, everything_once_only=True)

    def add_custom(self, attributes, inherited, extend=True, origin=None):
        """Record a custom object"""
        self.update('custom', attributes, inherited, extend=extend, origin=origin, each_once_only=True, store_with_origin=True)

    def add_components(self, components, inherited, extend=True, origin=None):
        """Record components"""
        adding = self.update("components", components, inherited, extend=extend, origin=origin, prefix="components", manually_update=True)
        for identity, kls in adding.items():
            name = identity[len("components."):]
            self.components[identity] = ((name, kls, {}), origin)

    def added_attributes(self, attributes, origin):
        """Record added attributes"""
        if not attributes:
            return

        self.debug("Adding attrs", attributes=attributes, origin=origin)
        if origin not in self.added:
            self.added[origin] = []

        conflicts = set(self.added[origin]) - set(attributes)
        if conflicts:
            raise DevelopeError("Adding variable already added by the metaclass somewhere", origin=origin)

        self.added[origin].extend(attributes)

    def removed_attributes(self, attributes, origin):
        """Record removed attributes"""
        if not attributes:
            return

        self.debug("Removing attrs", attributes=attributes, origin=origin)
        if origin not in self.removed:
            self.removed[origin] = []

        self.removed[origin].extend(attributes)

    def replaced_attributes(self, attributes, origin):
        """Record replaced attrs"""
        if not attributes:
            return

        self.debug("Replacing attrs", attributes=attributes, origin=origin)
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
        if identity in base.__dict__ and base.__dict__[identity] is None:
            return

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

            if identity in added and bookkeeper.value_for(identity, added[identity]) is not None:
                return added[identity]
            if identity in replaced and bookkeeper.value_for(identity, replaced[identity]) is not None:
                return replaced[identity]

        if identity in base.__dict__ and base.__dict__[identity] is not None:
            return base

        for parent in from_mro(base.__class__, not_self=True):
            found = self.find_adder(identity, parent)
            if found:
                return found

    def find_remover(self, identity, base):
        """Determine what in the mro added this particular attribute"""
        if identity in base.__dict__ and base.__dict__[identity] is None:
            return base

        bookkeeper = getattr(base, '__bookkeeper__', None)
        if bookkeeper:
            added = {}
            for origin, keys in bookkeeper.added.items():
                for key in keys:
                    added[key] = origin

            removed = {}
            for origin, keys in bookkeeper.removed.items():
                for key in keys:
                    removed[key] = origin

            replaced = {}
            for origin, keys in bookkeeper.replaced.items():
                for key in keys:
                    replaced[key] = origin

            if identity in added and bookkeeper.value_for(identity, added[identity]) is None:
                return added[identity]
            if identity in replaced and bookkeeper.value_for(identity, replaced[identity]) is None:
                return replaced[identity]
            if identity in removed:
                return removed[identity]

        for parent in from_mro(base.__class__, not_self=True):
            found = self.find_remover(identity, parent)
            if found:
                return found
