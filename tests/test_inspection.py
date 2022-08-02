from dataclasses import dataclass
import datetime
import enum
import sys
import unittest
from typing import Dict, List, NamedTuple, Optional, Union

from strong_typing.auxiliary import Annotated, typeannotation
from strong_typing.inspection import (
    get_class_properties,
    get_module_classes,
    get_referenced_types,
    is_dataclass_type,
    is_generic_dict,
    is_generic_list,
    is_named_tuple_type,
    is_type_enum,
    is_type_optional,
    is_type_union,
    unwrap_generic_dict,
    unwrap_generic_list,
)


class Side(enum.Enum):
    "An enumeration with string values."

    LEFT = "L"
    RIGHT = "R"


class Suit(enum.Enum):
    "An enumeration with numeric values."

    Diamonds = 1
    Hearts = 2
    Clubs = 3
    Spades = 4


class SimpleObject:
    "A value of a fundamental type wrapped into an object."

    value: int = 0


@dataclass
class SimpleDataClass:
    "A value of a fundamental type wrapped into an object."

    value: int = 0


class SimpleNamedTuple(NamedTuple):
    integer: int
    string: str


@typeannotation
class SimpleAnnotation:
    pass


class TestInspection(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(get_referenced_types(type(None)), [])
        self.assertEqual(get_referenced_types(int), [int])
        self.assertEqual(get_referenced_types(Optional[str]), [str])
        self.assertEqual(get_referenced_types(List[str]), [str])
        self.assertEqual(get_referenced_types(Dict[int, bool]), [int, bool])
        self.assertEqual(get_referenced_types(Union[int, bool, str]), [int, bool, str])
        self.assertEqual(
            get_referenced_types(Union[None, int, datetime.datetime]),
            [int, datetime.datetime],
        )

    def test_enum(self):
        self.assertTrue(is_type_enum(Side))
        self.assertTrue(is_type_enum(Suit))
        self.assertFalse(is_type_enum(Side.LEFT))
        self.assertFalse(is_type_enum(Suit.Diamonds))
        self.assertFalse(is_type_enum(int))
        self.assertFalse(is_type_enum(str))
        self.assertFalse(is_type_enum(SimpleObject))

    def test_optional(self):
        self.assertTrue(is_type_optional(Optional[int]))
        self.assertTrue(is_type_optional(Union[None, int]))
        self.assertTrue(is_type_optional(Union[int, None]))

        if sys.version_info >= (3, 10):
            self.assertTrue(is_type_optional(None | int))
            self.assertTrue(is_type_optional(int | None))

        self.assertFalse(is_type_optional(int))
        self.assertFalse(is_type_optional(Union[int, str]))

    def test_strict_optional(self):
        self.assertTrue(is_type_optional(Union[None, int], strict=True))
        self.assertTrue(is_type_optional(Union[int, None], strict=True))
        self.assertTrue(is_type_optional(Union[None, int, str]))
        self.assertTrue(is_type_optional(Union[int, None, str]))
        self.assertFalse(is_type_optional(Union[None, int, str], strict=True))
        self.assertFalse(is_type_optional(Union[int, None, str], strict=True))

    def test_union(self):
        self.assertTrue(is_type_union(Union[int, str]))
        self.assertTrue(is_type_union(Union[bool, int, str]))
        self.assertTrue(is_type_union(Union[int, str, None]))
        self.assertTrue(is_type_union(Union[bool, int, str, None]))

        if sys.version_info >= (3, 10):
            self.assertTrue(is_type_union(int | str))
            self.assertTrue(is_type_union(bool | int | str))
            self.assertTrue(is_type_union(int | str | None))
            self.assertTrue(is_type_union(bool | int | str | None))

        self.assertFalse(is_type_union(int))

    def test_list(self):
        self.assertTrue(is_generic_list(List[int]))
        self.assertTrue(is_generic_list(List[str]))
        self.assertTrue(is_generic_list(List[SimpleObject]))
        self.assertFalse(is_generic_list(list))
        self.assertFalse(is_generic_list([]))

        self.assertEqual(unwrap_generic_list(List[int]), int)
        self.assertEqual(unwrap_generic_list(List[str]), str)
        self.assertEqual(unwrap_generic_list(List[List[str]]), List[str])

    def test_dict(self):
        self.assertTrue(is_generic_dict(Dict[int, str]))
        self.assertTrue(is_generic_dict(Dict[str, SimpleObject]))
        self.assertFalse(is_generic_dict(dict))
        self.assertFalse(is_generic_dict({}))

        self.assertEqual(unwrap_generic_dict(Dict[int, str]), (int, str))
        self.assertEqual(
            unwrap_generic_dict(Dict[str, SimpleObject]), (str, SimpleObject)
        )
        self.assertEqual(
            unwrap_generic_dict(Dict[str, List[SimpleObject]]),
            (str, List[SimpleObject]),
        )

    def test_annotated(self):
        self.assertTrue(is_type_enum(Annotated[Suit, SimpleAnnotation()]))
        self.assertTrue(is_generic_list(Annotated[List[int], SimpleAnnotation()]))
        self.assertTrue(is_generic_dict(Annotated[Dict[int, str], SimpleAnnotation()]))

    def test_classes(self):
        classes = get_module_classes(sys.modules[__name__])
        self.assertCountEqual(
            classes,
            [
                Side,
                Suit,
                SimpleAnnotation,
                SimpleObject,
                SimpleDataClass,
                SimpleNamedTuple,
                TestInspection,
            ],
        )

    def test_properties(self):
        properties = [
            (name, data_type) for name, data_type in get_class_properties(SimpleObject)
        ]
        self.assertCountEqual(properties, [("value", int)])

        self.assertTrue(is_dataclass_type(SimpleDataClass))
        properties = [
            (name, data_type)
            for name, data_type in get_class_properties(SimpleDataClass)
        ]
        self.assertCountEqual(properties, [("value", int)])

        self.assertTrue(is_named_tuple_type(SimpleNamedTuple))
        properties = [
            (name, data_type)
            for name, data_type in get_class_properties(SimpleNamedTuple)
        ]
        self.assertCountEqual(properties, [("integer", int), ("string", str)])


if __name__ == "__main__":
    unittest.main()
