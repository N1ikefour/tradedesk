"""Шифрование credentials счёта: envelope AES-256-GCM (SPEC.md 3.2).

⚠️ `MASTER_KEY` после первой записи credentials не меняется и не теряется. Потерянный ключ
означает, что пароли всех счетов нечитаемы навсегда: восстановить их неоткуда, резервная
копия БД без ключа бесполезна. Единственный законный способ сменить ключ —
`scripts/rotate_master_key.py`, и до коммита каждой его транзакции смена обратима.

Схема хранения. Пароль шифруется одноразовым `data_key` — своим на каждую запись, — а
мастер-ключом шифруется только сам `data_key`. Отсюда два свойства. Компрометация одного
`data_key` стоит один счёт, а не все. И ротация перешифровывает короткий `wrapped_data_key`,
**не читая и не переписывая `ciphertext` вовсе**: на тысяче счетов это разница между
секундами и часами и между «обрыв на середине безопасен» и «часть данных перешифрована».

    ciphertext        = 0x01 | nonce(12) | AES-256-GCM(data_key, padded_json, aad_credentials)
    wrapped_data_key  = 0x01 | nonce(12) | AES-256-GCM(master_key, data_key, aad_data_key)

Первый байт — версия формата блоба; колонка `key_version` — **отпечаток мастер-ключа**,
это разные вещи. Отпечаток вычисляется из самого ключа (`key_fingerprint`), а не назначается
человеком: значение в колонке физически не может разойтись с тем, чем строка обёрнута,
и ротации незачем гадать, какой ключ подойдёт.

Nonce у каждого блоба свой, из `secrets.token_bytes`, и хранится рядом с шифротекстом:
выводить его из данных нельзя, повтор nonce на одном ключе разрушает GCM.

AAD привязывает оба блоба к `account_id` — иначе строку одного счёта можно переставить
в другой, и она расшифруется. В `SPEC.md` 3.2 этого нет, решение принято в S0-05.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, NamedTuple
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import ConfigError, Settings, get_settings

# Версия формата блоба. Меняется, только если меняется раскладка байт, — не при ротации.
FORMAT_VERSION = 1

NONCE_LENGTH = 12
TAG_LENGTH = 16
DATA_KEY_LENGTH = 32
MASTER_KEY_LENGTH = 32

# Длина шифротекста GCM равна длине открытого текста, то есть выдаёт длину пароля тому,
# кто дорвался до дампа БД. Открытый текст дополняется до кратного этому блоку.
PAD_BLOCK = 64
# Префикс с настоящей длиной полезной части, big-endian.
PAD_HEADER_LENGTH = 4

# Отпечаток мастер-ключа кладётся в `key_version` — колонку `smallint`, то есть знаковый
# int16. Берём 15 бит: значение всегда неотрицательное и в диапазон помещается с запасом.
FINGERPRINT_MASK = 0x7FFF
# Домен персонализации blake2s: отпечаток из этой функции ни с чем другим не совпадёт.
_FINGERPRINT_PERSON = b"td-mk-fp"

# Домены AAD: один и тот же account_id, но блоб внешнего слоя нельзя подставить во внутренний.
_AAD_CREDENTIALS = b"tradedesk:credentials:v1:"
_AAD_DATA_KEY = b"tradedesk:data-key:v1:"

# Единственный текст ошибки расшифровки на все причины: не сошёлся тег, не та версия формата,
# блоб обрезан, JSON не разобрался. По сообщению не должно быть видно, что именно не сошлось.
DECRYPTION_FAILED = "Не удалось расшифровать credentials счёта"

_MASTER_KEY_FORMAT = "ожидается base64 от 32 случайных байт"


class CredentialsKeyError(ConfigError):
    """Мастер-ключ отсутствует или задан не в том формате. Значение ключа сюда не попадает.

    Наследник `ConfigError`: непригодный ключ — это отказ конфигурации, и гейт старта
    обрабатывает его тем же путём, что пустой `SECRET_KEY`.
    """


class CredentialsDecryptionError(RuntimeError):
    """Расшифровка не удалась. Причина наружу не раскрывается — см. DECRYPTION_FAILED."""


def key_fingerprint(material: bytes) -> int:
    """15-битный отпечаток мастер-ключа — то, что лежит в колонке `key_version`.

    Функция от ключа, а не счётчик в руках оператора: колонка не может соврать, какой
    ключ обернул строку, и весь класс ошибки «версию забыли поднять» исчезает.
    15 бит от 256-битного случайного ключа сами по себе не приближают к подбору: они
    говорят «какой из ключей», а не «какой ключ».
    """
    digest = hashlib.blake2s(material, digest_size=2, person=_FINGERPRINT_PERSON).digest()
    return int.from_bytes(digest, "big") & FINGERPRINT_MASK


@dataclass(frozen=True, repr=False)
class MasterKey:
    """Мастер-ключ. Номер версии не хранится — он вычисляется из материала.

    Свой `__repr__` обязателен: dataclass печатает поля, а `repr` объекта уезжает
    и в traceback, и в лог через `scrub_unserializable`.
    """

    material: bytes = field(repr=False)

    @property
    def version(self) -> int:
        return key_fingerprint(self.material)

    def __repr__(self) -> str:
        return f"MasterKey(version={self.version})"


@dataclass(frozen=True)
class MasterKeyring:
    """Текущий ключ и, на время ротации, предыдущий.

    Пока ротация не закончена, в таблице лежат строки обеих версий, и читать нужно уметь обе:
    иначе смена ключа выключает продукт на всё время миграции.
    """

    current: MasterKey
    previous: MasterKey | None = None

    def candidates(self, key_version: int) -> tuple[MasterKey, ...]:
        """Ключи в порядке попытки: сперва тот, чей отпечаток записан в строке.

        Остальные пробуются следом — на случай, когда значение в колонке испорчено помимо
        нашего кода: терять строку при живом ключе хуже, чем сделать лишнюю попытку.
        Перебор безопасен, неверный ключ отсекает тег GCM. Неудачи неотличимы **по тексту**;
        по времени отличимы (несовпадение версии формата отсекается раньше тега), но
        блобы приходят только из своей БД, и подавать их в оракул некому.
        """
        known = [key for key in (self.current, self.previous) if key is not None]
        return tuple(sorted(known, key=lambda key: key.version != key_version))


class EncryptedCredentials(NamedTuple):
    """Ровно то, что уходит в три колонки `account_credentials`."""

    ciphertext: bytes
    wrapped_data_key: bytes
    key_version: int


class WrappedDataKey(NamedTuple):
    """Результат перешифровки обёртки. `ciphertext` при этом не участвует вовсе."""

    wrapped_data_key: bytes
    key_version: int


def parse_master_key(raw: str, *, variable: str) -> bytes:
    """base64 от 32 байт. Ни значение, ни его длина в текст ошибки не попадают."""
    normalized = raw.strip().replace("-", "+").replace("_", "/")
    normalized += "=" * (-len(normalized) % 4)
    try:
        material = base64.b64decode(normalized, validate=True)
    except (binascii.Error, ValueError):
        raise CredentialsKeyError(f"{variable}: {_MASTER_KEY_FORMAT}") from None
    if len(material) != MASTER_KEY_LENGTH:
        raise CredentialsKeyError(f"{variable}: {_MASTER_KEY_FORMAT}") from None
    return material


def master_keyring(settings: Settings | None = None) -> MasterKeyring:
    """Связка ключей из окружения. Бросает `CredentialsKeyError` на непригодной конфигурации."""
    settings = settings or get_settings()
    current = MasterKey(
        parse_master_key(settings.master_key.get_secret_value(), variable="MASTER_KEY")
    )
    raw_previous = settings.master_key_previous.get_secret_value().strip()
    if not raw_previous:
        return MasterKeyring(current=current)
    previous = MasterKey(parse_master_key(raw_previous, variable="MASTER_KEY_PREVIOUS"))
    if hmac.compare_digest(previous.material, current.material):
        raise CredentialsKeyError(
            "MASTER_KEY_PREVIOUS совпадает с MASTER_KEY: ротировать нечего и не на что."
        )
    if previous.version == current.version:
        # 1 случай на 32768. Различить строки двух ключей было бы нечем, поэтому отказ
        # до начала ротации, а не «как-нибудь разберёмся по ходу».
        raise CredentialsKeyError(
            f"Отпечатки MASTER_KEY и MASTER_KEY_PREVIOUS совпали ({current.version}), "
            "хотя ключи разные: строки двух ключей стали бы неразличимы. "
            "Сгенерируй другой новый ключ и повтори."
        )
    return MasterKeyring(current=current, previous=previous)


def check_master_key(settings: Settings) -> None:
    """Гейт старта: в проде непригодный `MASTER_KEY` — отказ грузиться.

    Иначе битый ключ обнаружился бы не при запуске, а 500-й на первой записи credentials.
    В `local` не мешаем: секреты там появляются по мере надобности (та же логика, что
    у `check_production_secrets`).
    """
    if not settings.is_prod:
        return
    master_keyring(settings)


def master_key_scrub_values(settings: Settings) -> list[str]:
    """Написания мастер-ключей, которые логгер должен вырезать из любого текста.

    base64-форму регистрирует `Settings.scrubbable_secret_values`, но в коде ключ живёт
    как `bytes`, а `scrub_text` ищет подстроку: `repr(b"...")` с base64 не совпадёт.
    Регистрируются тело `repr` и hex — оба написания, в которых сырой ключ может утечь
    в лог под несекретным именем.
    """
    values: list[str] = []
    for raw in (settings.master_key, settings.master_key_previous):
        try:
            material = parse_master_key(raw.get_secret_value(), variable="MASTER_KEY")
        except CredentialsKeyError:
            continue
        values += [repr(material)[2:-1], material.hex()]
    return values


def encrypt_credentials(
    credentials: Mapping[str, str],
    *,
    account_id: UUID,
    keyring: MasterKeyring | None = None,
) -> EncryptedCredentials:
    """Шифрует `{"password": …}` под свежим `data_key`.

    `account_id` обязателен: он уходит в AAD обоих слоёв. Два вызова на одних и тех же
    данных дают разные шифротексты — иначе по равенству блобов видно, что у двух счетов
    один пароль.

    Бросает `CredentialsKeyError`, если мастер-ключ непригоден, и `TypeError`, если
    в значениях пришло не строковое.
    """
    for name, value in credentials.items():
        if not isinstance(value, str):
            raise TypeError(f"credentials[{name!r}]: ожидается str")
    keyring = keyring or master_keyring()
    payload = _dump_payload(credentials)
    # Свой data_key на каждую запись: иначе компрометация одного ключа вскрывает все счета.
    data_key = secrets.token_bytes(DATA_KEY_LENGTH)
    return EncryptedCredentials(
        ciphertext=_seal(data_key, _pad(payload), _aad(_AAD_CREDENTIALS, account_id)),
        wrapped_data_key=_seal(keyring.current.material, data_key, _aad(_AAD_DATA_KEY, account_id)),
        key_version=keyring.current.version,
    )


def decrypt_credentials(
    ciphertext: bytes,
    wrapped_data_key: bytes,
    key_version: int,
    *,
    account_id: UUID,
    keyring: MasterKeyring | None = None,
) -> dict[str, str]:
    """Обратно к `{"password": …}`. Принимает распакованный `EncryptedCredentials`.

    Любая неудача — `CredentialsDecryptionError` с одним и тем же текстом: испорченный байт,
    чужой счёт в `account_id`, потерянный ключ и битый JSON снаружи неотличимы. Ничего
    не логирует: открытый текст на этом пути в руках, и попасть в лог он не должен никак.
    """
    keyring = keyring or master_keyring()
    data_key, _ = _unwrap_data_key(wrapped_data_key, key_version, account_id, keyring)
    payload = _unpad(_open(data_key, ciphertext, _aad(_AAD_CREDENTIALS, account_id)))
    return _load_payload(payload)


def rewrap_data_key(
    wrapped_data_key: bytes,
    key_version: int,
    *,
    account_id: UUID,
    keyring: MasterKeyring | None = None,
) -> WrappedDataKey:
    """Перешифровывает обёртку `data_key` текущим мастер-ключом. `ciphertext` не нужен.

    Идемпотентна по смыслу: строка, уже обёрнутая текущим ключом, возвращается как есть,
    байт в байт, — повторный прогон ротации ничего не переписывает.
    """
    keyring = keyring or master_keyring()
    data_key, source = _unwrap_data_key(wrapped_data_key, key_version, account_id, keyring)
    if source.version == keyring.current.version and key_version == keyring.current.version:
        return WrappedDataKey(wrapped_data_key, key_version)
    return WrappedDataKey(
        _seal(keyring.current.material, data_key, _aad(_AAD_DATA_KEY, account_id)),
        keyring.current.version,
    )


def opening_master_key(
    wrapped_data_key: bytes,
    key_version: int,
    *,
    account_id: UUID,
    keyring: MasterKeyring | None = None,
) -> MasterKey:
    """Каким из ключей связки открывается обёртка. Сам `data_key` наружу не отдаётся.

    Нужна проверяющему проходу ротации: он сверяет, что строка открывается текущим ключом
    и что отпечаток в колонке совпадает с открывшим ключом.
    """
    keyring = keyring or master_keyring()
    _, key = _unwrap_data_key(wrapped_data_key, key_version, account_id, keyring)
    return key


def _dump_payload(credentials: Mapping[str, str]) -> bytes:
    """JSON в UTF-8. `surrogatepass` — на случай одиночного суррогата вида \\ud800:

    он приходит из JSON запроса, обычный `.encode()` уронил бы его UnicodeEncodeError.
    Экранировать всё подряд (`ensure_ascii=True`) нельзя: не-ASCII раздувается вшестеро,
    и по размеру блоба становится виден алфавит пароля, а не только длина.
    """
    dumped = json.dumps(
        dict(credentials), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return dumped.encode("utf-8", "surrogatepass")


def _load_payload(payload: bytes) -> dict[str, str]:
    try:
        decoded: Any = json.loads(payload.decode("utf-8", "surrogatepass"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CredentialsDecryptionError(DECRYPTION_FAILED) from None
    if not isinstance(decoded, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in decoded.items()
    ):
        raise CredentialsDecryptionError(DECRYPTION_FAILED)
    return decoded


def _aad(scope: bytes, account_id: UUID) -> bytes:
    return scope + str(account_id).encode()


def _seal(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    nonce = secrets.token_bytes(NONCE_LENGTH)
    return bytes([FORMAT_VERSION]) + nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def _open(key: bytes, blob: bytes, aad: bytes) -> bytes:
    if len(blob) < 1 + NONCE_LENGTH + TAG_LENGTH or blob[0] != FORMAT_VERSION:
        raise CredentialsDecryptionError(DECRYPTION_FAILED)
    nonce = blob[1 : 1 + NONCE_LENGTH]
    try:
        return AESGCM(key).decrypt(nonce, blob[1 + NONCE_LENGTH :], aad)
    except InvalidTag:
        raise CredentialsDecryptionError(DECRYPTION_FAILED) from None


def _unwrap_data_key(
    wrapped_data_key: bytes,
    key_version: int,
    account_id: UUID,
    keyring: MasterKeyring,
) -> tuple[bytes, MasterKey]:
    aad = _aad(_AAD_DATA_KEY, account_id)
    for key in keyring.candidates(key_version):
        try:
            return _open(key.material, wrapped_data_key, aad), key
        except CredentialsDecryptionError:
            continue
    raise CredentialsDecryptionError(DECRYPTION_FAILED)


def _pad(payload: bytes) -> bytes:
    size = PAD_HEADER_LENGTH + len(payload)
    padded_size = -(-size // PAD_BLOCK) * PAD_BLOCK
    return len(payload).to_bytes(PAD_HEADER_LENGTH, "big") + payload + bytes(padded_size - size)


def _unpad(padded: bytes) -> bytes:
    if len(padded) < PAD_HEADER_LENGTH:
        raise CredentialsDecryptionError(DECRYPTION_FAILED)
    size = int.from_bytes(padded[:PAD_HEADER_LENGTH], "big")
    if size > len(padded) - PAD_HEADER_LENGTH:
        raise CredentialsDecryptionError(DECRYPTION_FAILED)
    return padded[PAD_HEADER_LENGTH : PAD_HEADER_LENGTH + size]
