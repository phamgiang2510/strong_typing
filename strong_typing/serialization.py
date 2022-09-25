import base64
import dataclasses
import datetime
import enum
import inspect
import json
import typing
import uuid
from typing import Any, Dict, List, Set, TextIO, Tuple, Type, TypeVar, Union

from .core import JsonType
from .deserializer import create_deserializer
from .exception import JsonKeyError, JsonTypeError, JsonValueError
from .inspection import (
    create_object,
    get_class_properties,
    get_resolved_hints,
    is_dataclass_instance,
    is_dataclass_type,
    is_named_tuple_instance,
    is_named_tuple_type,
    is_reserved_property,
    is_type_optional,
    unwrap_optional_type,
)
from .mapping import python_id_to_json_field
from .name import python_type_to_str

T = TypeVar("T")


def object_to_json(obj: Any) -> JsonType:
    """
    Converts a Python object to a representation that can be exported to JSON.

    * Fundamental types (e.g. numeric types) are written as is.
    * Date and time types are serialized in the ISO 8601 format with time zone.
    * A byte array is written as a string with Base64 encoding.
    * UUIDs are written as a UUID string.
    * Enumerations are written as their value.
    * Containers (e.g. `list`, `dict`, `set`, `tuple`) are exported recursively.
    * Objects with properties (including data class types) are converted to a dictionaries of key-value pairs.
    """

    # check for well-known types
    if obj is None:
        # can be directly represented in JSON
        return None
    elif isinstance(obj, (bool, int, float, str)):
        # can be directly represented in JSON
        return obj
    elif isinstance(obj, bytes):
        return base64.b64encode(obj).decode("ascii")
    elif isinstance(obj, datetime.datetime):
        if obj.tzinfo is None:
            raise JsonValueError(
                f"timestamp lacks explicit time zone designator: {obj}"
            )
        fmt = obj.isoformat()
        if fmt.endswith("+00:00"):
            fmt = f"{fmt[:-6]}Z"  # Python's isoformat() does not support military time zones like "Zulu" for UTC
        return fmt
    elif isinstance(obj, (datetime.date, datetime.time)):
        return obj.isoformat()
    elif isinstance(obj, uuid.UUID):
        return str(obj)
    elif isinstance(obj, enum.Enum):
        return obj.value
    elif isinstance(obj, list):
        return [object_to_json(item) for item in obj]
    elif isinstance(obj, dict):
        if obj and isinstance(next(iter(obj.keys())), enum.Enum):
            generator = (
                (key.value, object_to_json(value)) for key, value in obj.items()
            )
        else:
            generator = (
                (str(key), object_to_json(value)) for key, value in obj.items()
            )
        return dict(generator)
    elif isinstance(obj, set):
        return [object_to_json(item) for item in obj]

    # check if object has custom serialization method
    convert_func = getattr(obj, "to_json", None)
    if callable(convert_func):
        return convert_func()

    if is_dataclass_instance(obj):
        object_dict = {}
        for field in dataclasses.fields(obj):
            value = getattr(obj, field.name)
            if value is None:
                continue
            object_dict[
                python_id_to_json_field(field.name, field.type)
            ] = object_to_json(value)
        return object_dict

    elif is_named_tuple_instance(obj):
        object_dict = {}
        field_names: Tuple[str, ...] = type(obj)._fields
        for field_name in field_names:
            value = getattr(obj, field_name)
            if value is None:
                continue
            object_dict[python_id_to_json_field(field_name)] = object_to_json(value)
        return object_dict

    elif isinstance(obj, tuple):
        # check plain tuple after named tuple, named tuples are also instances of tuple
        return [object_to_json(item) for item in obj]

    # fail early if caller passes an object with an exotic type
    if (
        inspect.isfunction(obj)
        or inspect.ismodule(obj)
        or inspect.isclass(obj)
        or inspect.ismethod(obj)
    ):
        raise TypeError(f"object of type {type(obj)} cannot be represented in JSON")

    # iterate over object attributes to get a standard representation
    object_dict = {}
    for name in dir(obj):
        if is_reserved_property(name):
            continue

        value = getattr(obj, name)
        if value is None:
            continue

        # filter instance methods
        if inspect.ismethod(value):
            continue

        object_dict[python_id_to_json_field(name)] = object_to_json(value)

    return object_dict


def _as_json_list(typ: type, data: JsonType) -> List[JsonType]:
    if isinstance(data, list):
        return data
    else:
        type_name = python_type_to_str(typ)
        raise JsonTypeError(
            f"type `{type_name}` expects JSON `array` data but instead received: {data}"
        )


def _as_json_dict(typ: type, data: JsonType) -> Dict[str, JsonType]:
    if isinstance(data, dict):
        return data
    else:
        type_name = python_type_to_str(typ)
        raise JsonTypeError(
            f"`type `{type_name}` expects JSON `object` data but instead received: {data}"
        )


def json_to_object(typ: Type[T], data: JsonType) -> T:
    """
    Creates an object from a representation that has been de-serialized from JSON.

    When de-serializing a JSON object into a Python object, the following transformations are applied:

    * Fundamental types are parsed as `bool`, `int`, `float` or `str`.
    * Date and time types are parsed from the ISO 8601 format with time zone into the corresponding Python type
      `datetime`, `date` or `time`
    * A byte array is read from a string with Base64 encoding into a `bytes` instance.
    * UUIDs are extracted from a UUID string into a `uuid.UUID` instance.
    * Enumerations are instantiated with a lookup on enumeration value.
    * Containers (e.g. `list`, `dict`, `set`, `tuple`) are parsed recursively.
    * Complex objects with properties (including data class types) are populated from dictionaries of key-value pairs
      using reflection (enumerating type annotations).

    :raises TypeError: A de-serializing engine cannot be constructed for the input type.
    :raises JsonKeyError: Deserialization for a class or union type has failed because a matching member was not found.
    :raises JsonTypeError: Deserialization for data has failed due to a type mismatch.
    """

    parser = create_deserializer(typ)
    return parser.parse(data)


def _json_to_object(typ: Type[T], data: JsonType) -> T:
    # check for well-known types
    if typ is type(None):
        if data is not None:
            raise JsonTypeError(
                f"`None` type expects JSON `null` but instead received: {data}"
            )
        return typing.cast(T, None)
    elif typ is bool:
        if not isinstance(data, bool):
            raise JsonTypeError(
                f"`bool` type expects JSON `boolean` data but instead received: {data}"
            )
        return typing.cast(T, bool(data))
    elif typ is int:
        if not isinstance(data, int):
            raise JsonTypeError(
                f"`int` type expects integer data as JSON `number` but instead received: {data}"
            )
        return typing.cast(T, int(data))
    elif typ is float:
        if not isinstance(data, float) and not isinstance(data, int):
            raise JsonTypeError(
                f"`int` type expects data as JSON `number` but instead received: {data}"
            )
        return typing.cast(T, float(data))
    elif typ is str:
        if not isinstance(data, str):
            raise JsonTypeError(
                f"`str` type expects JSON `string` data but instead received: {data}"
            )
        return typing.cast(T, str(data))
    elif typ is bytes:
        if not isinstance(data, str):
            raise JsonTypeError(
                f"`bytes` type expects JSON `string` data but instead received: {data}"
            )
        return typing.cast(T, base64.b64decode(data))
    elif typ is datetime.datetime or typ is datetime.date or typ is datetime.time:
        if not isinstance(data, str):
            raise JsonTypeError(
                f"`{typ.__name__}` type expects JSON `string` data but instead received: {data}"
            )
        if typ is datetime.datetime:
            if data.endswith("Z"):
                data = f"{data[:-1]}+00:00"  # Python's isoformat() does not support military time zones like "Zulu" for UTC
            timestamp = datetime.datetime.fromisoformat(data)
            if timestamp.tzinfo is None:
                raise JsonValueError(
                    f"timestamp lacks explicit time zone designator: {data}"
                )
            return typing.cast(T, timestamp)
        elif typ is datetime.date:
            return typing.cast(T, datetime.date.fromisoformat(data))
        elif typ is datetime.time:
            return typing.cast(T, datetime.time.fromisoformat(data))
    elif typ is uuid.UUID:
        if not isinstance(data, str):
            raise JsonTypeError(
                f"`{typ.__name__}` type expects JSON `string` data but instead received: {data}"
            )
        return typing.cast(T, uuid.UUID(data))

    # generic types (e.g. list, dict, set, etc.)
    origin_type = typing.get_origin(typ)
    if origin_type is list:
        (list_type,) = typing.get_args(typ)  # unpack single tuple element
        json_list_data: List[JsonType] = _as_json_list(typ, data)
        list_value = [json_to_object(list_type, item) for item in json_list_data]
        return typing.cast(T, list_value)
    elif origin_type is dict:
        key_type, value_type = typing.get_args(typ)
        json_dict_data: Dict[str, JsonType] = _as_json_dict(typ, data)
        dict_value = dict(
            (key_type(key), json_to_object(value_type, value))
            for key, value in json_dict_data.items()
        )
        return typing.cast(T, dict_value)
    elif origin_type is set:
        (set_type,) = typing.get_args(typ)  # unpack single tuple element
        json_set_data: List[JsonType] = _as_json_list(typ, data)
        set_value = set(json_to_object(set_type, item) for item in json_set_data)
        return typing.cast(T, set_value)
    elif origin_type is tuple:
        json_tuple_data: List[JsonType] = _as_json_list(typ, data)
        tuple_value = tuple(
            json_to_object(member_type, item)
            for (member_type, item) in zip(
                (member_type for member_type in typing.get_args(typ)),
                (item for item in json_tuple_data),
            )
        )
        return typing.cast(T, tuple_value)
    elif origin_type is Union:
        for t in typing.get_args(typ):
            # iterate over potential types of discriminated union
            try:
                return json_to_object(t, data)
            except (JsonKeyError, JsonTypeError) as k:
                # indicates a required field is missing from JSON dict -OR- the data cannot be cast to the expected type,
                # i.e. we don't have the type that we are looking for
                continue

        raise JsonKeyError(f"type `{typ}` could not be instantiated from: {data}")

    if not inspect.isclass(typ):
        if is_dataclass_instance(typ):
            raise TypeError(f"dataclass type expected but got instance: {typ}")
        else:
            raise TypeError(f"unable to de-serialize unrecognized type {typ}")

    if is_named_tuple_type(typ):
        json_named_tuple_data: Dict[str, JsonType] = _as_json_dict(typ, data)
        object_dict = {
            field_name: json_to_object(field_type, json_named_tuple_data[field_name])
            for field_name, field_type in typing.get_type_hints(typ).items()
        }
        tuple_value = typ(**object_dict)  # type: ignore
        return typing.cast(T, tuple_value)

    if issubclass(typ, enum.Enum):
        enum_value = typ(data)
        return typing.cast(T, enum_value)

    # check if object has custom serialization method
    convert_func = getattr(typ, "from_json", None)
    if callable(convert_func):
        return convert_func(data)

    if is_dataclass_type(typ):
        json_field_data: Dict[str, JsonType] = _as_json_dict(typ, data)
        assigned_names: Set[str] = set()
        resolved_hints = get_resolved_hints(typ)
        obj = create_object(typ)
        for field in dataclasses.fields(typ):
            field_type = resolved_hints[field.name]
            json_name = python_id_to_json_field(field.name, field_type)
            assigned_names.add(json_name)

            if json_name in json_field_data:
                if is_type_optional(field_type):
                    required_type: type = unwrap_optional_type(field_type)
                else:
                    required_type = field_type

                field_value: Any = json_to_object(
                    required_type, json_field_data[json_name]
                )
            elif field.default is not dataclasses.MISSING:
                field_value = field.default
            elif field.default_factory is not dataclasses.MISSING:
                field_value = field.default_factory()
            else:
                if is_type_optional(field_type):
                    field_value = None
                else:
                    raise JsonKeyError(
                        f"missing required property `{json_name}` from JSON object: {data}"
                    )

            # bypass custom __init__ in dataclass
            setattr(obj, field.name, field_value)

        unassigned_names = [
            json_name
            for json_name in json_field_data
            if json_name not in assigned_names
        ]
        if unassigned_names:
            raise JsonKeyError(
                f"unrecognized fields in JSON object: {unassigned_names}"
            )

        return typing.cast(T, obj)

    json_data: Dict[str, JsonType] = _as_json_dict(typ, data)
    obj = create_object(typ)
    for property_name, property_type in get_class_properties(typ):
        json_name = python_id_to_json_field(property_name, property_type)

        if is_type_optional(property_type):
            if json_name in json_data:
                required_type = unwrap_optional_type(property_type)
                property_value: Any = json_to_object(
                    required_type, json_data[json_name]
                )
            else:
                property_value = None
        else:
            if json_name in json_data:
                property_value = json_to_object(property_type, json_data[json_name])
            else:
                raise JsonKeyError(
                    f"missing required property `{json_name}` from JSON object: {data}"
                )

        setattr(obj, property_name, property_value)

    return typing.cast(T, obj)


def json_dump_string(json_object: JsonType) -> str:
    "Dump an object as a JSON string with a compact representation."

    return json.dumps(
        json_object, ensure_ascii=False, check_circular=False, separators=(",", ":")
    )


def json_dump(json_object: JsonType, file: TextIO) -> None:
    json.dump(
        json_object,
        file,
        ensure_ascii=False,
        check_circular=False,
        separators=(",", ":"),
    )
    file.write("\n")
