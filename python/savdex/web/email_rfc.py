"""
Правило email у Laravel (без параметров или «rfc») — validateEmail с
RFCValidation из egulias/email-validator 4.x.

Перенесено из vendor/egulias/email-validator/src как есть, со всеми
странностями: адрес неверен только при ошибке разбора, предупреждения
(длинная локальная часть, адрес длиннее 254 байт, комментарии, IP без
тега и т. п.) его не портят. Предупреждения здесь не собираются вовсе:
на ответ они не влияют, а побочных действий у их проверок нет.

Лексер — AbstractLexer из doctrine/lexer: preg_split по шаблону
EmailLexer с флагами iu. Каждый символ за пределами ASCII — отдельная
лексема; исключение — «ſ» (U+017F) и знак кельвина (U+212A): при /i
класс [a-zA-Z] их тоже берёт, и они склеиваются с латиницей в одно
слово. Лексема из одних символов категорий S и C (эмодзи, «€»,
управляющие, неназначенные) — INVALID, и тогда адрес неверен целиком.
Категории берутся из unicodedata: у Python 3.11 это Unicode 14.0, как у
PCRE2 10.42 у здешнего PHP (у других версий расходятся только символы,
назначенные в новых версиях Unicode).

Длина метки домена с не-ASCII символами у PHP считается через
idn_to_ascii (ICU, UTS #46, переходная обработка): ошибка
LABEL_TOO_LONG. Здесь повторён ход ICU (uts46.cpp, punycode.cpp);
таблица сопоставления UTS #46 — из пакета idna. Если ICU не смог
выдать ответ (итог длиннее 254 байт), $idnaInfo у PHP пуст, обращение
к ключу даёт предупреждение, Laravel превращает его в ErrorException,
а RFCValidation — в ошибку: адрес неверен.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

import idna

# Типы лексем — константы EmailLexer
S_EMPTY = -1
C_NUL = 0
S_HTAB = 9
S_LF = 10
S_CR = 13
S_SP = 32
EXCLAMATION = 33
S_DQUOTE = 34
NUMBER_SIGN = 35
DOLLAR = 36
PERCENTAGE = 37
AMPERSAND = 38
S_SQUOTE = 39
S_OPENPARENTHESIS = 40
S_CLOSEPARENTHESIS = 41
ASTERISK = 42
S_PLUS = 43
S_COMMA = 44
S_HYPHEN = 45
S_DOT = 46
S_SLASH = 47
S_COLON = 58
S_SEMICOLON = 59
S_LOWERTHAN = 60
S_EQUAL = 61
S_GREATERTHAN = 62
QUESTIONMARK = 63
S_AT = 64
S_OPENBRACKET = 91
S_BACKSLASH = 92
S_CLOSEBRACKET = 93
CARET = 94
S_UNDERSCORE = 95
S_BACKTICK = 96
S_OPENCURLYBRACES = 123
S_PIPE = 124
S_CLOSECURLYBRACES = 125
S_TILDE = 126
INVERT_QUESTIONMARK = 168
INVERT_EXCLAMATION = 173
GENERIC = 300
S_IPV6TAG = 301
INVALID = 302
CRLF = 1310
S_DOUBLECOLON = 5858

#: EmailLexer::$charValue. Ключи '' и '\0' (в одинарных кавычках PHP —
#: обратная косая и ноль) лексемой не бывают никогда, но оставлены как есть
CHAR_VALUE: dict[str, int] = {
    "{": S_OPENCURLYBRACES,
    "}": S_CLOSECURLYBRACES,
    "(": S_OPENPARENTHESIS,
    ")": S_CLOSEPARENTHESIS,
    "<": S_LOWERTHAN,
    ">": S_GREATERTHAN,
    "[": S_OPENBRACKET,
    "]": S_CLOSEBRACKET,
    ":": S_COLON,
    ";": S_SEMICOLON,
    "@": S_AT,
    "\\": S_BACKSLASH,
    "/": S_SLASH,
    ",": S_COMMA,
    ".": S_DOT,
    "'": S_SQUOTE,
    "`": S_BACKTICK,
    '"': S_DQUOTE,
    "-": S_HYPHEN,
    "::": S_DOUBLECOLON,
    " ": S_SP,
    "\t": S_HTAB,
    "\r": S_CR,
    "\n": S_LF,
    "\r\n": CRLF,
    "IPv6": S_IPV6TAG,
    "": S_EMPTY,
    "\\0": C_NUL,
    "*": ASTERISK,
    "!": EXCLAMATION,
    "&": AMPERSAND,
    "^": CARET,
    "$": DOLLAR,
    "%": PERCENTAGE,
    "~": S_TILDE,
    "|": S_PIPE,
    "_": S_UNDERSCORE,
    "=": S_EQUAL,
    "+": S_PLUS,
    "¿": INVERT_QUESTIONMARK,
    "?": QUESTIONMARK,
    "#": NUMBER_SIGN,
    "¡": INVERT_EXCLAMATION,
}

#: [a-zA-Z] под флагами iu у PCRE2: ещё «ſ» и знак кельвина
_LETTERS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ\u017f\u212a")
_DIGITS = frozenset("0123456789")

#: LocalPart::INVALID_TOKENS
_LOCAL_INVALID = frozenset(
    {S_COMMA, S_CLOSEBRACKET, S_OPENBRACKET, S_GREATERTHAN, S_LOWERTHAN, S_COLON, S_SEMICOLON}
    | {INVALID}
)

#: FoldingWhiteSpace::FWS_TYPES
_FWS_TYPES = frozenset({S_SP, S_HTAB, S_CR, S_LF, CRLF})

#: Недопустимое внутри кавычек без экранирования (DoubleQuote::$invalid)
_DQUOTE_INVALID = frozenset({C_NUL, S_HTAB, S_CR, S_LF})

#: DomainPart::DOMAIN_MAX_LENGTH и LABEL_MAX_LENGTH
DOMAIN_MAX_LENGTH = 253
LABEL_MAX_LENGTH = 63


@dataclass(frozen=True, eq=False)
class _Token:
    """Doctrine\\Common\\Lexer\\Token: значение и тип (позиция не нужна)."""

    value: str
    type: int


#: Пустая лексема EmailLexer ($nullToken): конец ввода
_NULL = _Token("", S_EMPTY)


def _type(value: str) -> int:
    """EmailLexer::getType.

    mb_convert_encoding из Windows-1252 срабатывает только на чистом
    ASCII — там он ничего не меняет.
    """
    if value in CHAR_VALUE:
        return CHAR_VALUE[value]

    if value == "\0":
        return C_NUL

    # isInvalidChar: в строке нет ни одного символа вне \p{S} и \p{C}
    if all(unicodedata.category(c)[0] in "SC" for c in value):
        return INVALID

    return GENERIC


def _scan(text: str) -> list[_Token]:
    """AbstractLexer::scan: preg_split по шаблону EmailLexer.

    (?:[a-zA-Z]+[46]?)|[^\\x00-\\x7F]|[0-9]+|\\r\\n|::|\\s+?|. — именно в
    этом порядке; некатчабельный [\\xA0-\\xff]+ до дела не доходит:
    любой не-ASCII символ раньше забирает вторая ветка.
    """
    tokens = []
    i = 0
    n = len(text)

    while i < n:
        c = text[i]
        j = i + 1

        if c in _LETTERS:
            while j < n and text[j] in _LETTERS:
                j += 1
            if j < n and text[j] in "46":
                j += 1
        elif c in _DIGITS:
            while j < n and text[j] in _DIGITS:
                j += 1
        elif (c == "\r" and text[j : j + 1] == "\n") or (c == ":" and text[j : j + 1] == ":"):
            j += 1

        value = text[i:j]
        tokens.append(_Token(value, _type(value)))
        i = j

    return tokens


class _Lexer:
    """EmailLexer поверх AbstractLexer — только то, что нужно разбору."""

    def __init__(self, tokens: list[_Token]) -> None:
        self.tokens = tokens
        self.position = 0
        self.lookahead: _Token | None = None
        self.current = _NULL
        self.previous = _NULL
        self.recording = False
        self.accumulator: list[str] = []

    def move_next(self) -> bool:
        if self.recording and self.previous is _NULL:
            self.accumulator.append(self.current.value)

        self.previous = self.current

        # AbstractLexer::moveNext; пустой lookahead EmailLexer заменяет
        # на $nullToken, так что token никогда не null
        token = self.lookahead if self.lookahead is not None else _NULL

        if self.position < len(self.tokens):
            self.lookahead = self.tokens[self.position]
            self.position += 1
        else:
            self.lookahead = None

        self.current = token

        if self.recording:
            self.accumulator.append(self.current.value)

        return self.lookahead is not None

    def is_next(self, *types: int) -> bool:
        return self.lookahead is not None and self.lookahead.type in types

    def find(self, type_: int) -> bool:
        """EmailLexer::find без исключения: есть ли такая лексема от lookahead до конца.

        У PHP это skipUntil на копии лексера; lookahead — всегда
        tokens[position - 1].
        """
        if self.lookahead is None:
            return False

        return any(t.type == type_ for t in self.tokens[self.position - 1 :])

    def start_recording(self) -> None:
        self.accumulator = []
        self.recording = True

    def escaped(self) -> bool:
        """PartParser::escaped."""
        return self.previous.type == S_BACKSLASH and self.current.type != GENERIC


def _fws(lx: _Lexer) -> bool:
    """FoldingWhiteSpace::parse."""
    if lx.escaped() or lx.current.type not in _FWS_TYPES:
        return True

    previous = lx.previous

    # checkCRLFInFWS
    if lx.current.type == CRLF and not lx.is_next(S_SP, S_HTAB):
        return False

    if lx.current.type == S_CR:
        return False

    if lx.is_next(GENERIC) and previous.type != S_AT:
        return False

    return lx.current.type not in (S_LF, C_NUL)


def _comment(lx: _Lexer, *, domain: bool) -> bool:
    """Comment::parse со стратегией LocalComment или DomainComment."""
    opened = 0

    if lx.current.type == S_OPENPARENTHESIS:
        opened += 1
        if not lx.find(S_CLOSEPARENTHESIS):
            return False

    if lx.current.type == S_CLOSEPARENTHESIS:
        return False

    def go_on() -> bool:
        # exitCondition: «true» — продолжать
        if domain:
            return not (opened == 0 and lx.is_next(S_DOT))
        return not lx.is_next(S_AT)

    more = True
    while go_on() and more:
        if lx.is_next(S_OPENPARENTHESIS):
            opened += 1
        if lx.is_next(S_CLOSEPARENTHESIS):
            opened -= 1
        more = lx.move_next()

    if opened != 0:
        return False

    # endOfLoopValidations
    return lx.is_next(S_DOT if domain else S_AT)


def _check_dquote(lx: _Lexer) -> bool:
    """DoubleQuote::checkDQUOTE."""
    if lx.is_next(GENERIC) and lx.previous.type == GENERIC:
        return False

    return lx.find(S_DQUOTE)


def _double_quote(lx: _Lexer) -> bool:
    """DoubleQuote::parse."""
    if not _check_dquote(lx):
        return False

    lx.move_next()

    while lx.current.type not in (S_DQUOTE, S_EMPTY):
        if lx.current.type == S_BACKSLASH and lx.is_next(S_DQUOTE):
            lx.move_next()

        lx.move_next()

        if not lx.escaped() and lx.current.type in _DQUOTE_INVALID:
            return False

    prev = lx.previous

    if prev.type == S_BACKSLASH and not _check_dquote(lx):
        return False

    return lx.is_next(S_AT) or prev.type == S_BACKSLASH


def _local_part(lx: _Lexer) -> bool:
    """LocalPart::parse."""
    lx.start_recording()

    while lx.current.type not in (S_AT, S_EMPTY):
        # hasDotAtStart
        if lx.current.type == S_DOT and lx.previous.type == S_EMPTY:
            return False

        if lx.current.type == S_DQUOTE and not _double_quote(lx):
            return False

        if lx.current.type in (S_OPENPARENTHESIS, S_CLOSEPARENTHESIS) and not _comment(
            lx, domain=False
        ):
            return False

        if lx.current.type == S_DOT and lx.is_next(S_DOT, S_AT):
            return False

        # validateEscaping
        if lx.current.type == S_BACKSLASH and lx.is_next(GENERIC):
            return False

        if lx.current.type in _LOCAL_INVALID:
            return False

        if not _fws(lx):
            return False

        lx.move_next()

    # Длина локальной части — только предупреждение
    lx.recording = False
    return True


def _domain_literal(lx: _Lexer) -> bool:
    """DomainPart::parseDomainLiteral и DomainLiteral::parse.

    Всё про IPv4/IPv6 в DomainLiteral — только предупреждения; разбор
    FWS внутри скобок ничего не двигает, его итог отбрасывается.
    """
    if not lx.find(S_CLOSEBRACKET):
        return False

    while True:
        if lx.current.type == C_NUL:
            return False

        if lx.is_next(S_OPENBRACKET):
            return False

        if lx.is_next(S_CR):
            return False

        if lx.current.type == S_BACKSLASH:
            return False

        if lx.current.type == S_CLOSEBRACKET or not lx.move_next():
            return True


def _domain_body(lx: _Lexer) -> bool:
    """DomainPart::doParseDomainPart."""
    has_comments = False
    # $this->label: копится со всеми лексемами метки, точка — первой
    label = ""

    while True:
        prev = lx.previous

        # checkNotAllowedChars
        if lx.current.type in (S_BACKSLASH, S_SLASH):
            return False

        if lx.current.type in (S_OPENPARENTHESIS, S_CLOSEPARENTHESIS):
            has_comments = True
            if not _comment(lx, domain=True):
                return False

        # checkConsecutiveDots
        if lx.current.type == S_DOT and lx.is_next(S_DOT):
            return False

        if lx.current.type == S_OPENBRACKET:
            return _domain_literal(lx)

        # checkLabelLength
        if lx.current.type == S_DOT:
            if _label_too_long(label):
                return False
            label = ""
        label += lx.current.value

        if not _fws(lx):
            return False

        # checkDomainPartExceptions
        if lx.current.type == S_OPENBRACKET and prev.type != S_AT:
            return False

        if lx.current.type == S_HYPHEN and lx.is_next(S_DOT):
            return False

        if lx.current.type == S_BACKSLASH and lx.is_next(GENERIC):
            return False

        # validateTokens
        allowed = lx.current.type in (GENERIC, S_HYPHEN, S_DOT) or (
            has_comments and lx.current.type in (S_OPENPARENTHESIS, S_CLOSEPARENTHESIS)
        )
        if not allowed:
            return False

        lx.move_next()

        if lx.current.type == S_EMPTY:
            break

    return not _label_too_long(label)


def _domain_part(lx: _Lexer) -> bool:
    """DomainPart::parse."""
    lx.start_recording()
    lx.move_next()

    # performDomainStartChecks
    if lx.current.type in (S_DOT, S_HYPHEN):
        return False

    if lx.current.type == S_EMPTY or (lx.current.type == S_SP and not lx.is_next(GENERIC)):
        return False

    if lx.current.type == S_AT:
        return False

    if not _domain_body(lx):
        return False

    # checkEndOfDomain
    if lx.previous.type in (S_DOT, S_HYPHEN) or lx.current.type == S_SP:
        return False

    lx.recording = False
    domain = "".join(lx.accumulator)

    return len(domain.encode()) <= DOMAIN_MAX_LENGTH


def _label_too_long(label: str) -> bool:
    """DomainPart::isLabelTooLong."""
    if label.isascii():
        return len(label) > LABEL_MAX_LENGTH

    return _idn_label_too_long(label)


# --- idn_to_ascii($label, IDNA_DEFAULT, INTL_IDNA_VARIANT_UTS46) по ICU ---

#: Ответ ICU длиннее буфера PHP (255 байт) — idn_to_ascii возвращает false
_IDN_BUFFER = 255
#: punycode.cpp: ENCODE_MAX_CODE_UNITS и DECODE_MAX_CHARS
_ENCODE_MAX = 1000
_DECODE_MAX = 2000
_LDH = frozenset("-0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
#: Отклонения UTS #46 при переходной обработке (UTS46::mapDevChars)
_DEVIATIONS = {"ß": "ss", "ς": "σ", "\u200c": "", "\u200d": ""}


class _IcuError(Exception):
    """ICU вернул ошибку — PHP получит false и пустой $idnaInfo."""


def _utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def _uts46_normalize(s: str) -> str:
    """Нормализатор uts46 у ICU: сопоставление и NFC, отклонения не трогает.

    Запрещённые символы ICU заменяет на U+FFFD, пропускаемые убирает.
    Без правил STD3: скобки, пробел и прочий ASCII остаются.
    """
    out = []

    for c in s:
        try:
            out.append(idna.uts46_remap(c, std3_rules=False))
        except idna.IDNAError:
            out.append("\ufffd")

    return unicodedata.normalize("NFC", "".join(out))


def _uts46_map(s: str) -> str:
    """UTS46::processUnicode до разбивки на метки: сопоставление, затем отклонения."""
    mapped = _uts46_normalize(s)

    if any(c in _DEVIATIONS for c in mapped):
        mapped = "".join(_DEVIATIONS.get(c, c) for c in mapped)
        mapped = _uts46_normalize(mapped)

    return mapped


def _decode_digit(c: str) -> int:
    """punycode.cpp: decodeDigit."""
    cp = ord(c)

    if cp <= ord("Z"):
        if cp <= ord("9"):
            return -1 if cp < ord("0") else cp - ord("0") + 26
        return cp - ord("A")

    if cp <= ord("z"):
        return cp - ord("a")

    return -1


def _adapt_bias(delta: int, length: int, first: bool) -> int:
    """punycode.cpp: adaptBias."""
    delta = delta // 700 if first else delta // 2
    delta += delta // length
    count = 0

    while delta > (35 * 26) // 2:
        delta //= 35
        count += 36

    return count + (36 * delta) // (delta + 38)


def _punycode_decode(src: str) -> str | None:
    """punycode.cpp: u_strFromPunycode; None — ошибка."""
    if _utf16_len(src) > _DECODE_MAX:
        return None

    basic_length = max(src.rfind("-"), 0)

    if not src[:basic_length].isascii():
        return None

    out = list(src[:basic_length])
    n = 0x80
    i = 0
    bias = 72
    count = basic_length
    pos = basic_length + 1 if basic_length > 0 else 0

    while pos < len(src):
        oldi = i
        w = 1
        k = 36

        while True:
            if pos >= len(src):
                return None

            digit = _decode_digit(src[pos])
            pos += 1

            if digit < 0 or digit > (0x7FFFFFFF - i) // w:
                return None

            i += digit * w
            t = k - bias
            if t < 1:
                t = 1
            elif k >= bias + 26:
                t = 26

            if digit < t:
                break

            if w > 0x7FFFFFFF // (36 - t):
                return None

            w *= 36 - t
            k += 36

        count += 1
        bias = _adapt_bias(i - oldi, count, oldi == 0)

        if i // count > 0x7FFFFFFF - n:
            return None

        n += i // count
        i %= count

        if n > 0x10FFFF or 0xD800 <= n <= 0xDFFF:
            return None

        out.insert(i, chr(n))
        i += 1

    return "".join(out)


def _leading_mark(label: str) -> bool:
    return unicodedata.category(label[0]).startswith("M")


def _bad_ace(label: str) -> tuple[str, bool]:
    """UTS46::markBadACELabel: (что попадёт в ответ, LABEL_TOO_LONG)."""
    rest = label[4:]

    if all(c in _LDH for c in rest):
        return label + "\ufffd", False

    return label, rest.isascii() and _utf16_len(label) > LABEL_MAX_LENGTH


def _process_label(label: str) -> tuple[str, bool]:
    """UTS46::processLabel для toASCII: (что попадёт в ответ, LABEL_TOO_LONG)."""
    if not label:
        return label, False

    if label.startswith("xn--"):
        if len(label) == 4 or (len(label) > 5 and label.endswith("-")):
            return _bad_ace(label)

        decoded = _punycode_decode(label[4:])

        if decoded is None or _uts46_normalize(decoded) != decoded:
            return _bad_ace(label)

        # Точка, U+FFFD и ведущая комбинирующая — тяжёлые ошибки
        if "." in decoded or "\ufffd" in decoded or _leading_mark(decoded):
            return _bad_ace(label)

        return label, _utf16_len(label) > LABEL_MAX_LENGTH

    if _leading_mark(label):
        return "\ufffd" + label[1:], False

    if "\ufffd" in label:
        return label, False

    if label.isascii():
        return label, len(label) > LABEL_MAX_LENGTH

    if _utf16_len(label) > _ENCODE_MAX:
        raise _IcuError

    encoded = "xn--" + label.encode("punycode").decode("ascii")

    return encoded, len(encoded) > LABEL_MAX_LENGTH


def _idn_label_too_long(label: str) -> bool:
    """idn_to_ascii(...)['errors'] & IDNA_ERROR_LABEL_TOO_LONG.

    Метка у DomainPart начинается с точки (кроме первой), так что ICU
    видит пустую метку и саму метку; точки дают и символы вроде «。».
    """
    too_long = False
    out = []

    try:
        for part in _uts46_map(label).split("."):
            text, error = _process_label(part)
            out.append(text)
            too_long = too_long or error
    except _IcuError:
        return True

    # Ответ не влез в буфер PHP: $idnaInfo пуст, Laravel ловит
    # предупреждение как исключение — адрес неверен
    if len(".".join(out).encode()) >= _IDN_BUFFER:
        return True

    return too_long


def rfc_valid(email: str) -> bool:
    """EmailValidator::isValid($email, new RFCValidation)."""
    try:
        email.encode()
    except UnicodeEncodeError:
        # Одиночные суррогаты: в PHP это был бы неверный UTF-8, preg_split
        # вернул бы false, весь ввод стал бы одной лексемой без «@»
        return False

    tokens = _scan(email)

    if any(t.type == INVALID for t in tokens):
        return False

    lx = _Lexer(tokens)

    # preLeftParsing / hasAtToken: первая лексема — «@»
    lx.move_next()
    lx.move_next()
    if lx.current.type == S_AT:
        return False

    return _local_part(lx) and _domain_part(lx)


def is_valid(value: object) -> bool:
    """ValidatesAttributes::validateEmail без параметров (или «rfc»)."""
    if not isinstance(value, str):
        return False

    if "\r" in value or "\n" in value:
        return False

    return rfc_valid(value)
