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
    show_first = ['origin', 'added_by', 'removed_by']

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

        first = []
        cleaned = self.clean_attrs(self.kwargs)
        for special in self.show_first:
            if special in cleaned:
                value = cleaned[special]
                del cleaned[special]
                first.append((special, value))

        if first:
            if not message or message[-1] != '\n':
                message = "{}\n".format(message)
            message = "{}{}".format(message, self.format_kwargs(first).lstrip())

        if hasattr(self, 'extra_message'):
            if not message or message[-1] != '\n':
                message = "{}\n".format(message)
            message = "{}{}".format(message, self.extra_message(cleaned).lstrip())

        return message

    def clean_attrs(self, kwargs):
        """Clean attributes"""
        cleaned = {}
        for key, val in kwargs.items():
            method = "clean_{}".format(key)
            if hasattr(self, method):
                val = getattr(self, method)(key, val, kwargs)
            cleaned[key] = val
        return cleaned

    def get_position_for_cleaner(self, key, val, kwargs):
        from introspection import position_for
        return position_for(val)
    clean_origin = get_position_for_cleaner
    clean_added_by = get_position_for_cleaner
    clean_removed_by = get_position_for_cleaner

    def format_kwargs(self, kwargs, exclude=None):
        """Default extra message just adds on all the kwargs"""
        if exclude is None:
            exclude = []

        items = kwargs
        if type(kwargs) is dict:
            items = sorted(kwargs.items())

        return '\n'.join("{}='{}'".format(k, v) for k, v in items if k not in exclude)

    def extra_message(self, cleaned):
        """Default to showing all extra kwargs without the show_first stuff"""
        done = []
        custom = ""
        if hasattr(self, 'custom_extra'):
            custom, done = self.custom_extra(cleaned)

        others = self.format_kwargs(cleaned, exclude=self.show_first + done)
        return "{}{}".format(custom, others)

class UnexpectedValueError(DeveloperError):
    def custom_extra(self, cleaned):
        msg = dedent("""
            app='{app}'
            identity='{identity}'
            """.format(**cleaned)
            )
        return msg, ['app', 'identity']

class RequirementError(DeveloperError):
    path_desc = "requires"

    def clean_attrs(self, kwargs):
        kwargs['path_desc'] = self.path_desc
        return super(RequirementError, self).clean_attrs(kwargs)

    def clean_identity(self, key, val, kwargs):
        if not val:
            val = ''
        return val

    def clean_found(self, key, val, kwargs):
        if not val:
            val = ''
        if type(val) in (list, tuple):
            val = '.'.join(val)
        return val

    def custom_extra(self, cleaned):
        msg = dedent("""
            {path_desc}='{path}'
            base='{base}'
            found='{found}'
            identity='{identity}'
            """.format(**cleaned)
            )
        return msg, ['path_desc', 'path', 'base', 'found', 'identity']

class RequirementAttributeError(RequirementError):
    def custom_extra(self, cleaned):
        msg = dedent("""
            {path_desc}='{path}'
            obj='{obj}'
            requires_obj_attribute='{requires}'
            found='{found}'
            identity='{identity}'
            """.format(**cleaned)
            )
        return msg, ['path_desc', 'path', 'obj', 'requires', 'found', 'identity']
