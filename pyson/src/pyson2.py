from dataclasses import dataclass
from enum import Enum, auto
from time import time
from typing import Any, Callable, Literal, TypeVar, Union

Value = Union[str, int, float, "Array", "Object", None, Literal[True], Literal[False]]
Object = dict[str, Value]
Array = list[Value]
JSON = Array | Object


class TokenType(Enum):
    L_CURLY = auto()
    R_CURLY = auto()
    L_BRACKET = auto()
    R_BRACKET = auto()
    COLON = auto()
    COMMA = auto()
    STRING = auto()
    NUMBER = auto()
    BOOLEAN = auto()
    NULL = auto()
    EMPTY = auto()


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str | None = None


WHITESPACE = set(" \b\t\r\n\f")
HEXDIGITS = set("0123456789abcdefABCDEF")
DIGITS = set("0123456789")
NUMERIC = set("0123456789.eE+-")


T = TypeVar("T")
Func = Callable[..., Any]


class SimpleHashMap:
    def __init__(self, hash_func: Callable[[T], int], items: list[T]) -> None:
        pass


class Matcher:
    def __init__(self, cases: dict[str, Func]) -> None:
        self.cases = cases

    def __getitem__(self, key: str) -> Func | None:
        return self.cases.get(key, None)

    def get(self, value: str) -> Func | None:
        return self.cases.get(value, None)


def l_curly(i: int, *_: Any) -> tuple[Token, int]:
    return Token(TokenType.L_CURLY), i + 1


def r_curly(i: int, *_: Any) -> tuple[Token, int]:
    return Token(TokenType.R_CURLY), i + 1


def l_bracket(i: int, *_: Any) -> tuple[Token, int]:
    return Token(TokenType.L_BRACKET), i + 1


def r_bracket(i: int, *_: Any) -> tuple[Token, int]:
    return Token(TokenType.R_BRACKET), i + 1


def colon(i: int, *_: Any) -> tuple[Token, int]:
    return Token(TokenType.COLON), i + 1


def comma(i: int, *_: Any) -> tuple[Token, int]:
    return Token(TokenType.COMMA), i + 1


def true(i: int, json: str, _: Matcher) -> tuple[Token, int]:
    _true = json[i : i + 4]
    if _true != "true":
        raise ValueError("Invalid true value")
    return Token(TokenType.BOOLEAN, "true"), i + 4


def false(i: int, json: str, _: Matcher) -> tuple[Token, int]:
    _false = json[i : i + 5]
    if _false != "false":
        raise ValueError("Invalid false value")
    return Token(TokenType.BOOLEAN, "false"), i + 5


def null(i: int, json: str, _: Matcher) -> tuple[Token, int]:
    _null = json[i : i + 4]
    if _null != "null":
        raise ValueError("Invalid null value")
    return Token(TokenType.NULL, "null"), i + 4


def number(i: int, json: str, _: Matcher) -> tuple[Token, int]:
    start = i
    while json[i] in NUMERIC:
        i += 1

    return Token(TokenType.NUMBER, json[start:i]), i


def string_replacement(i: int, idx: int, json: str) -> tuple[Token, int]:
    idx += 1
    string = (
        json[i:idx]
        .replace("\\\\", "\\")
        .replace('\\"', '"')
        .replace("\\/", "/")
        .replace("\\b", "\b")
        .replace("\\f", "\f")
        .replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
        .replace("\\u", "u")
    )
    return Token(TokenType.STRING, string), idx


def string_escaping(i: int, idx: int, json: str) -> tuple[Token, int]:
    n = json[idx + 1]
    match n:
        case '"' | "\\" | "/" | "b" | "f" | "n" | "r" | "t":
            idx += 2
        case "u":
            unicodes = json[idx + 2 : idx + 6]
            hx1, hx2, hx3, hx4 = unicodes.split("")
            if not (
                hx1 in HEXDIGITS
                and hx2 in HEXDIGITS
                and hx3 in HEXDIGITS
                and hx4 in HEXDIGITS
            ):
                raise ValueError("Invalid unicode sequence")
            idx += 6
        case _:
            raise ValueError("Invalid string escaping")
    return Token(TokenType.EMPTY), idx


def string(i: int, json: str, matcher: Matcher) -> tuple[Token, int]:
    idx = i + 1
    while json:
        func = matcher[json[idx]]
        if func:
            token, idx = func(
                i,
                idx,
                json,
            )
            if token.type != TokenType.EMPTY:
                return token, idx
        else:
            idx += 1
    return Token(TokenType.EMPTY), -1


lex_matchers: dict[str, Func] = {
    "{": l_curly,
    "}": r_curly,
    "[": l_bracket,
    "]": r_bracket,
    ":": colon,
    ",": comma,
    "t": true,
    "f": false,
    "n": null,
    '"': string,
    "0": number,
    "1": number,
    "2": number,
    "3": number,
    "4": number,
    "5": number,
    "6": number,
    "7": number,
    "8": number,
    "9": number,
    "-": number,
}

lex_string_matchers: dict[str, Func] = {'"': string_replacement, "\\": string_escaping}


def lex(json: str) -> list[Token]:
    tokens: list[Token] = []
    total_len = len(json)

    matcher = Matcher(lex_matchers)
    string_matcher = Matcher(lex_string_matchers)
    i = 0
    while i < total_len:
        func = matcher[json[i]]
        if func:
            token, i = func(i, json, string_matcher)
            tokens.append(token)
        else:
            i += 1

    return tokens


class Parser:
    def _error(self, msg: str) -> str:
        prior_tokens = self.tokens[self.i - 2 : self.i]
        return f"{msg}, {prior_tokens=}, {self.i=}, value={self.tokens[self.i]}"

    def parse_value(self) -> Value:
        value: Value = None
        v = self.tokens[self.i]
        match v.type:
            case TokenType.STRING:
                self.i += 1
                value = v.value
            case TokenType.NUMBER:
                self.i += 1
                assert v.value  # mypy fix
                as_float = float(v.value)
                value = as_float if "." in v.value else int(as_float)
            case TokenType.L_CURLY:
                value = self.parse_object()
            case TokenType.L_BRACKET:
                value = self.parse_array()
            case TokenType.BOOLEAN:
                self.i += 1
                value = True if v.value == "true" else False
            case TokenType.NULL:
                self.i += 1
            case _:
                raise ValueError(self._error("Unknown tokentype"))

        if self.tokens[self.i].type == TokenType.COMMA:
            self.i += 1

        return value

    def parse_object(self) -> Object:
        self.i += 1
        result: Object = {}
        known_keys: set[str] = set()

        while self.i < self.length:
            _type = self.tokens[self.i].type
            match _type:
                case TokenType.R_CURLY:
                    self.i += 1
                    break
                case TokenType.STRING:
                    key = self.tokens[self.i].value
                    assert key  # mypy fix
                    if key in known_keys:
                        raise ValueError(self._error("Duplicate key found"))
                    known_keys.add(key)
                    self.i += 1

                    if self.tokens[self.i].type != TokenType.COLON:
                        raise ValueError(self._error("Expected colon"))
                    self.i += 1

                    value = self.parse_value()
                    result[key] = value
                case _:
                    raise ValueError(self._error("Invalid object content"))

        return result

    def parse_array(self) -> Array:
        self.i += 1
        result: Array = []
        while self.i < self.length:
            _type = self.tokens[self.i].type
            match _type:
                case TokenType.R_BRACKET:
                    self.i += 1
                    break
                case _:
                    result.append(self.parse_value())
        return result

    def parse(self, tokens: list[Token]) -> JSON:
        self.tokens = tokens
        self.length = len(tokens)

        if len(tokens) < 2:
            raise ValueError(self._error("Too short to be valid"))

        self.i = 0
        _type = self.tokens[self.i].type
        match _type:
            case TokenType.L_CURLY:
                return self.parse_object()
            case TokenType.L_BRACKET:
                return self.parse_array()
            case _:
                raise ValueError(self._error("Invalid input"))


def loads(json: str) -> JSON:
    return Parser().parse(lex(json))


if __name__ == "__main__":
    from platform import system

    TEST_FILE_PREFIX = ""

    os_type = system()
    if os_type == "Linux":
        TEST_FILE_PREFIX = "/home/dimi"
    elif os_type == "Darwin":
        TEST_FILE_PREFIX = "/Users/dimitriosvalodimos"
    else:
        print("Wow... now you're using Windows?!")

    with open(
        f"{TEST_FILE_PREFIX}/work/poly-glotson/testfiles/large-file.json", "r"
    ) as f:
        json = f.read()

    timing = []
    for _ in range(20):
        start = time()
        value: JSON = loads(json)
        timing.append(time() - start)
    print(timing)
    print(sum(timing) / len(timing))
