from textwrap import dedent
import copy

class NotFound(Exception):
    def __init__(self, *args, **kwargs):
        self.base = kwargs.get('base')
        self.path = kwargs.get('path')
        self.found = kwargs.get('found')
        super(NotFound, self).__init__(*args)

class DeveloperError(Exception):
    desc = ""

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        super(DeveloperError, self).__init__(*args)

    def __str__(self):
        try:
            message = self.generate_message()
        except Exception as error:
            import traceback
            message = "Problem making exception\n{}".format(traceback.format_exc())
        return message

    def generate_message(self):
        message = super(DeveloperError, self).__str__()
        if not message:
            message = self.desc
        elif self.desc:
            message = "{} : {}".format(self.desc, message)

        if 'origin' in self.kwargs:
            from introspection import position_for
            origin = position_for(self.kwargs.get('origin'))
            if not message or message[-1] != '\n':
                message = "{}\n".format(message)
            message = "{}origin='{}'".format(message, origin)

        if hasattr(self, 'extra_message'):
            if not message or message[-1] != '\n':
                message = "{}\n".format(message)
            message = "{}{}".format(message, self.extra_message().lstrip())

        return message

    def extra_message(self):
        """Default extra message just adds on all the kwargs"""
        return '\n'.join("{}='{}'".format(k, v) for k, v in sorted(self.kwargs.items()) if k != 'origin')

class RequirementError(DeveloperError):
    path_desc = "requires"

    def clean_attrs(self):
        kwargs = copy.copy(self.kwargs)
        kwargs['path_desc'] = self.path_desc

        found = kwargs.get('found')
        origin = kwargs.get('origin')
        identity = kwargs.get("identity")

        if not found:
            found = ''
        if type(found) in (list, tuple):
            found = '.'.join(found)
        kwargs['found'] = found

        if not identity:
            identity = ''
        kwargs['identity'] = identity

        return kwargs

    def extra_message(self):
        values = self.clean_attrs()
        return dedent("""
            {path_desc}='{path}'
            base='{base}'
            found='{found}'
            identity='{identity}'
            """.format(**values)
            )

class RequirementAttributeError(RequirementError):
    def extra_message(self):
        values = self.clean_attrs()
        return dedent("""
            {path_desc}='{path}'
            obj='{obj}'
            requires_obj_attribute='{requires}'
            found='{found}'
            identity='{identity}'
            """.format(**values)
            )
