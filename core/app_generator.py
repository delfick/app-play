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
    def make_bookkeeper(self, name, methods, inherited, attrs):
        """Copy all bookkeeper stuff straight onto the class"""
        return self.copy_attributes_to_instance(name, methods, inherited, attrs)

    @not_extendable
    def make_methods(self, name, methods, inherited, attrs):
        """Create methods on the class that delegate to particular attributes"""
        return self.copy_attributes_to_instance(name, methods, inherited, attrs, generate_method=self.generate_method_delegate)

    @not_nullable
    def make_attrs(self, name, spec, inherited, attrs):
        """"Tell bookkeeper about attrs we want"""
        self.add_to_bookkeeper(name, spec, inherited, attrs, bookkeeper_method="add_attrs")

    @not_nullable
    def make_install(self, name, spec, inherited, attrs):
        """Determine what needs to be installed on the instance"""
        self.add_to_bookkeeper(name, spec, inherited, attrs, bookkeeper_method="add_installers")

    @not_nullable
    def make_components(self, name, spec, inherited, attrs):
        """"Tell bookkeeper about components we want"""
        self.add_to_bookkeeper(name, spec, inherited, attrs, bookkeeper_method="add_components")

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
