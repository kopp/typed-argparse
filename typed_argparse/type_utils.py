import sys
import typing
from typing import List, Optional, Tuple, Union, cast


_NoneType = type(None)


# It looks like there is no good type annotation that works for "type annotations".
# `type` would work for internal types (int, str, ...) and some typing.XXX types
# like typing.List and typing.Dict, but it doesn't work for typing.Optional and
# typing.Union. For now, let's make no assumptions at all.
RawTypeAnnotation = object


def _typename(t: RawTypeAnnotation) -> str:
    if hasattr(t, "__name__"):
        return f"'{getattr(t, '__name__')}'"
    else:
        return f"'{str(t)}'"


def _typename_of(value: object) -> str:
    return _typename(type(value))


def _get_origin(t: RawTypeAnnotation) -> Optional[object]:
    return cast(Optional[object], getattr(t, "__origin__", None))


def _get_args(t: RawTypeAnnotation) -> Tuple[RawTypeAnnotation, ...]:
    args = getattr(t, "__args__", ())
    if not isinstance(args, tuple):
        raise TypeError(
            f"Expected __args__ of type annotation to be a tuple, but it is {type(args)}"
        )
    return args


class TypeAnnotation:
    def __init__(self, raw_type: RawTypeAnnotation):
        self.raw_type: RawTypeAnnotation = raw_type
        self.origin = _get_origin(raw_type)
        self.args = _get_args(raw_type)

    def get_underlying_if_optional(self) -> Optional["TypeAnnotation"]:
        if self.origin is Union and len(self.args) == 2 and _NoneType in self.args:
            for t in self.args:
                if t != _NoneType:
                    return TypeAnnotation(t)
        return None

    def get_underlying_if_list(self) -> Optional["TypeAnnotation"]:
        # In Python 3.6 __origin__ is List
        # In Python 3.7+ __origin__ is list
        if (self.origin is List or self.origin is list) and len(self.args) >= 1:
            return TypeAnnotation(self.args[0])
        return None

    def validate(self, value: object) -> Tuple[object, Optional[str]]:

        # Handle optionals
        underlying_if_optional = self.get_underlying_if_optional()
        if underlying_if_optional is not None:
            if value is None:
                return value, None
            else:
                return underlying_if_optional.validate(value)

        # Handle lists
        underlying_if_list = self.get_underlying_if_list()
        if underlying_if_list is not None:
            if value is None:
                # Coerce empty list.
                return [], None
            elif not isinstance(value, list):
                # allowing isinstance(value, Iterable) seems too lose, because it would allow
                # to coerce a list from string, which is not desirable.
                return value, f"value is of type {_typename_of(value)}, expected 'list'"
            else:
                new_values = []
                for x in value:
                    new_value, error = underlying_if_list.validate(x)
                    if error is not None:
                        return value, f"not all elements of the list have proper type ({error})"
                    new_values.append(new_value)
                return new_values, None

        # Handle literals
        allowed_values_if_literal = _get_allowed_values_if_literal(self)
        if allowed_values_if_literal is not None:
            for allowed_value in allowed_values_if_literal:
                if value == allowed_value:
                    return value, None
            return (
                value,
                f"value {value} does not match any allowed literal value in "
                f"{allowed_values_if_literal}",
            )

        # TODO handle:
        # - Union
        # - Enum

        # We have to assert self.raw_type is a true `type`
        if not isinstance(self.raw_type, type):
            return (
                value,
                f"Type annotation is of type {_typename_of(self.raw_type)}, expected 'type'",
            )

        if isinstance(value, self.raw_type):
            return value, None
        else:
            return (
                value,
                f"value is of type {_typename_of(value)}, expected {_typename(self.raw_type)}",
            )


if sys.version_info[:2] == (3, 6):

    def _get_allowed_values_if_literal(t: TypeAnnotation) -> Optional[Tuple[object, ...]]:
        # In Python 3.6 Literal must come from typing_extensions. We use the simple
        # heuristic to look for __values__ directly without any instance checks.
        if hasattr(t.raw_type, "__values__"):
            values = getattr(t.raw_type, "__values__")
            if isinstance(values, tuple):
                return values
        return None


elif sys.version_info[:2] == (3, 7):

    def _get_allowed_values_if_literal(t: TypeAnnotation) -> Optional[Tuple[object, ...]]:
        # In Python 3.7 Literal must come from typing_extensions. In contrast to Python 3.6
        # it uses typing._GenericAlias and __args__ similar to other generics. This makes
        # it necessary to properly detect literal instance.

        try:
            import typing_extensions

            import_successful = True
        except ImportError:
            import_successful = False

        if import_successful:
            if t.origin is typing_extensions.Literal:
                return t.args

        return None


elif sys.version_info[:2] >= (3, 8):

    def _get_allowed_values_if_literal(t: TypeAnnotation) -> Optional[Tuple[object, ...]]:
        # In Python 3.8+, Literal has been integrated into typing itself.
        if t.origin is typing.Literal:
            return t.args
        else:
            return None


else:
    raise AssertionError(f"Python version {sys.version_info} is not supported")


def validate_value_against_type(
    arg_name: str,
    value: object,
    raw_type_annotation: RawTypeAnnotation,
) -> object:

    value, error = TypeAnnotation(raw_type_annotation).validate(value)

    if error is not None:
        raise TypeError(f"Failed to validate argument '{arg_name}': {error}")

    return value
