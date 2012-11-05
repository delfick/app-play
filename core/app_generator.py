from textwrap import dedent
import collections
import inspect

from errors import DeveloperError, NotFound, RequirementError
from decorators import not_extendable, not_nullable
from introspection import position_for, find_obj
from generator import SpecHandler

class AppHandler(SpecHandler):

    ########################
    ###   HANDLERS
    ########################

    @not_extendable
    def copy_attributes_to_instance(self, name, spec, inherited, attrs):
        """Just copy the attributes from the delaration onto the class"""
        attributes = self.nulls_if_necessary(spec, inherited)
        attributes.update(self.attributes_from(spec))
        self.replace_nulled_functions(attributes, inherited, attrs[name])
        return attributes
    make_attrs = copy_attributes_to_instance
    make_bookkeeper = copy_attributes_to_instance

    @not_nullable
    def make_install(self, name, spec, inherited, attrs):
        """Determine what needs to be installed on the instance"""
        attributes = {'_installers' : {key:val for key, val in spec.items() if not key.startswith("_")}}
        attributes['_installers']['__extend__'] = spec.get("__extend__", True)
        return attributes

    @not_nullable
    def make_components(self, name, spec, inherited, attrs):
        """"Create instance of defined components to be put on the class""" 
        values = spec
        if spec.get("__extends__", True):
            values = self.combine_dicts(inherited, spec)

        for key, kls in values.items():
            if not key.startswith("_"):
                if kls is not None and isinstance(kls, collections.Callable):
                    values[key] = kls()

        identity = name.lower()
        return {name.lower():type(identity, (object, ), values)}

    @not_extendable
    def create_methods(self, name, methods, inherited, attrs):
        """Create methods on the class that delegate to particular attributes"""
        attributes = self.nulls_if_necessary(methods, inherited)
        for ident, path in methods.items():
            if not ident.startswith("_"):
                if path is None:
                    attributes[ident] = path
                else:
                    attributes[ident] = self.generate_method_delegate(ident, path, name, attrs)
        self.replace_nulled_functions(attributes, inherited, attrs[name])
        return attributes

    ########################
    ###   GENERATORS
    ########################

    def generate_method_delegate(self, identity, path, name, attrs):
        """Generate a property that delegates to a particular path"""
        cached = {}
        def getter(app):
            """Lazily get value and complain if it can't be found"""
            if 'val' not in cached:
                try:
                    obj = find_obj(app, path)
                except NotFound as error:
                    raise DelegateRequirementError(origin=attrs[name], path=error.path, base=error.base, identity=identity, found=error.found)
                cached['val'] = obj

            # Return our cached value
            return cached['val']

        def setter(app, val):
            """Force the cached value"""
            cached['val'] = val

        # Return our delegate as a property
        return property(getter, setter)

    def generate_thing(self, name, spec, inherited, attrs):
        """Create an object from a single spec"""
        values = spec
        if spec.get("__extends__", True):
            values = self.combine_dicts(inherited, spec)

        if '__main__' not in spec:
            raise DeveloperError("Component {} needs to have a __main__ variable".format(name))

        kls = spec['__main__']
        kwargs = self.attributes_from(values)

        try:
            return kls(**kwargs)
        except Exception as error:
            import traceback
            error = "\n{}".format('\n'.join("\t{}".format(line) for line in dedent(traceback.format_exc()).split('\n')))
            raise DeveloperError("Failed to create custom object '{}'.".format(name)
                , error = error
                , origin = attrs[name]
                , calling = position_for(kls.__init__)
                , calling_with = kwargs
                , callee_signature = inspect.getargspec(kls.__init__)
                )
