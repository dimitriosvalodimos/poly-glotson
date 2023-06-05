from dataclasses import dataclass
from enum import Enum, auto
from time import time
from typing import Literal, Union

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


@dataclass(frozen=True)
class Token:
    type: TokenType
    start: int
    end: int


WHITESPACE = set(" \b\t\r\n\f")
HEXDIGITS = set("0123456789abcdefABCDEF")
DIGITS = set("0123456789")
NUMERIC = set("0123456789.eE+-")


def lex(json: str) -> list[Token]:
    tokens: list[Token] = []
    total_len = len(json)

    i = 0
    while i < total_len:
        value = json[i]
        match value:
            case "{":
                tokens.append(Token(TokenType.L_CURLY, i, i + 1))
                i += 1
            case "}":
                tokens.append(Token(TokenType.R_CURLY, i, i + 1))
                i += 1
            case "[":
                tokens.append(Token(TokenType.L_BRACKET, i, i + 1))
                i += 1
            case "]":
                tokens.append(Token(TokenType.R_BRACKET, i, i + 1))
                i += 1
            case ":":
                tokens.append(Token(TokenType.COLON, i, i + 1))
                i += 1
            case ",":
                tokens.append(Token(TokenType.COMMA, i, i + 1))
                i += 1
            case "t":
                true = json[i : i + 4]
                if true != "true":
                    raise ValueError("Invalid true value")
                tokens.append(Token(TokenType.BOOLEAN, i, i + 4))
                i += 4
            case "f":
                false = json[i : i + 5]
                if false != "false":
                    raise ValueError("Invalid false value")
                tokens.append(Token(TokenType.BOOLEAN, i, i + 5))
                i += 5
            case "n":
                null = json[i : i + 4]
                if null != "null":
                    raise ValueError("Invalid null value")
                tokens.append(Token(TokenType.NULL, i, i + 4))
                i += 4
            case '"':
                idx = i + 1
                while json:
                    v = json[idx]
                    match v:
                        case '"':
                            idx += 1
                            tokens.append(Token(TokenType.STRING, i, idx))
                            i = idx
                            break
                        case "\\":
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
                        case _:
                            idx += 1
            case _ as v if v in NUMERIC:
                start = i
                while json[i] in NUMERIC:
                    i += 1

                tokens.append(Token(TokenType.NUMBER, start, i))
            case _:
                i += 1

    return tokens


class Parser:
    def _error(self, msg: str) -> str:
        prior_tokens = self.tokens[self.i - 2 : self.i]
        return f"{msg}, {prior_tokens=}, {self.i=}, value={self.tokens[self.i]}"

    def normalized_string(self, t: Token) -> str:
        return (
            self.get_string(t)
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

    def get_string(self, t: Token) -> str:
        return self.json[t.start : t.end]

    def parse_value(self) -> Value:
        value: Value = None
        t = self.tokens[self.i]
        match t.type:
            case TokenType.STRING:
                self.i += 1
                value = self.normalized_string(t)
            case TokenType.NUMBER:
                self.i += 1
                string = self.get_string(t)
                as_float = float(string)
                value = as_float if "." in string else int(as_float)
            case TokenType.L_CURLY:
                self.i += 1
                value = self.parse_object()
            case TokenType.L_BRACKET:
                self.i += 1
                value = self.parse_array()
            case TokenType.BOOLEAN:
                self.i += 1
                string = self.get_string(t)
                value = True if string == "true" else False
            case TokenType.NULL:
                self.i += 1
            case _:
                raise ValueError(self._error("Unknown tokentype"))

        if self.tokens[self.i].type == TokenType.COMMA:
            self.i += 1

        return value

    def parse_object(self) -> Object:
        result: Object = {}
        known_keys: set[str] = set()

        while self.i < self.length:
            _type = self.tokens[self.i].type
            match _type:
                case TokenType.R_CURLY:
                    self.i += 1
                    break
                case TokenType.STRING:
                    key = self.normalized_string(self.tokens[self.i])
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

    def parse(self, json: str) -> JSON:
        self.tokens = lex(json)
        self.length = len(self.tokens)
        self.json = json

        if len(self.tokens) < 2:
            raise ValueError(self._error("Too short to be valid"))

        self.i = 1
        _type = self.tokens[0].type
        match _type:
            case TokenType.L_CURLY:
                return self.parse_object()
            case TokenType.L_BRACKET:
                return self.parse_array()
            case _:
                raise ValueError(self._error("Invalid input"))


def loads(json: str) -> JSON:
    return Parser().parse(json)


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
