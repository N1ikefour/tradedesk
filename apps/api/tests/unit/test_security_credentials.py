"""Envelope-шифрование credentials (S0-05).

Проверяется поведение наружу: round-trip, неразличимость одинаковых паролей, отказ
на любой порче байта и на подмене строки между счетами. Раскладка байт зафиксирована
отдельным тестом — её будет читать `S1-05`.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from uuid import UUID

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.logging import REDACTED, configure_logging, get_logger, register_secret_values
from app.core.security import (
    _AAD_CREDENTIALS,
    DECRYPTION_FAILED,
    FORMAT_VERSION,
    NONCE_LENGTH,
    PAD_BLOCK,
    PAD_HEADER_LENGTH,
    TAG_LENGTH,
    CredentialsDecryptionError,
    CredentialsKeyError,
    EncryptedCredentials,
    MasterKey,
    MasterKeyring,
    _aad,
    _pad,
    _seal,
    _unwrap_data_key,
    decrypt_credentials,
    encrypt_credentials,
    master_keyring,
    parse_master_key,
    rewrap_data_key,
)

KEY_V1 = bytes(range(32))
KEY_V2 = bytes(range(100, 132))

KEYRING_V1 = MasterKeyring(current=MasterKey(1, KEY_V1))
KEYRING_V2 = MasterKeyring(current=MasterKey(2, KEY_V2))
KEYRING_ROTATING = MasterKeyring(current=MasterKey(2, KEY_V2), previous=MasterKey(1, KEY_V1))

PASSWORD = "investor-пароль"
CREDENTIALS = {"password": PASSWORD}

ACCOUNT = UUID("11111111-1111-7111-8111-111111111111")
OTHER_ACCOUNT = UUID("22222222-2222-7222-8222-222222222222")

# Порча одного байта в каждой значимой части блоба.
DAMAGE_POSITIONS = [0, 1, 20, -17, -1]
DAMAGE_IDS = ["версия", "nonce", "тело", "тег", "конец"]


@pytest.fixture(autouse=True)
def _reset_registered_secrets() -> None:
    register_secret_values([])


def _encrypt(account_id: UUID = ACCOUNT) -> EncryptedCredentials:
    return encrypt_credentials(CREDENTIALS, account_id=account_id, keyring=KEYRING_V1)


def _decrypt(
    stored: EncryptedCredentials,
    account_id: UUID = ACCOUNT,
    keyring: MasterKeyring = KEYRING_V1,
) -> dict[str, str]:
    return decrypt_credentials(
        stored.ciphertext,
        stored.wrapped_data_key,
        stored.key_version,
        account_id=account_id,
        keyring=keyring,
    )


def _flip(blob: bytes, index: int) -> bytes:
    changed = bytearray(blob)
    changed[index] ^= 0x01
    return bytes(changed)


# --- round-trip ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "password",
    [
        "ascii-password",
        "инвестор-пароль",
        "кавычки \"двойные\" и 'одинарные'",
        "обратный\\слеш и \n перевод строки",
        "🙂 emoji и   пробелы",
        # Одиночный суррогат: JSON такое принимает, а .encode() без экранирования падает.
        "\ud800 битая пара",
        "",
        "x" * 4096,
    ],
    ids=["ascii", "cyrillic", "quotes", "escapes", "unicode", "surrogate", "empty", "long"],
)
def test_round_trip(password: str) -> None:
    stored = encrypt_credentials({"password": password}, account_id=ACCOUNT, keyring=KEYRING_V1)

    assert _decrypt(stored) == {"password": password}


def test_round_trip_keeps_all_keys() -> None:
    payload = {"password": PASSWORD, "note": "второе поле"}
    stored = encrypt_credentials(payload, account_id=ACCOUNT, keyring=KEYRING_V1)

    assert _decrypt(stored) == payload


def test_result_unpacks_as_tuple() -> None:
    """DoD спеки: `encrypt_credentials(dict) -> (ciphertext, wrapped_key)`.

    Третьим элементом идёт `key_version` — его тоже надо положить в строку таблицы.
    """
    ciphertext, wrapped_key, key_version = encrypt_credentials(
        CREDENTIALS, account_id=ACCOUNT, keyring=KEYRING_V1
    )

    assert isinstance(ciphertext, bytes)
    assert isinstance(wrapped_key, bytes)
    assert key_version == 1


def test_non_string_value_is_rejected() -> None:
    with pytest.raises(TypeError):
        encrypt_credentials({"password": 42}, account_id=ACCOUNT, keyring=KEYRING_V1)  # type: ignore[dict-item]


# --- неразличимость -----------------------------------------------------------------------


def test_same_credentials_encrypt_to_different_blobs() -> None:
    """Иначе по равенству блобов видно, что у двух счетов один и тот же пароль."""
    first = _encrypt()
    second = _encrypt()

    assert first.ciphertext != second.ciphertext
    assert first.wrapped_data_key != second.wrapped_data_key


def test_nonces_are_unique_across_encryptions() -> None:
    """Повтор nonce на одном ключе разрушает GCM целиком."""
    blobs = [_encrypt() for _ in range(200)]
    nonces = {blob.ciphertext[1 : 1 + NONCE_LENGTH] for blob in blobs}
    wrap_nonces = {blob.wrapped_data_key[1 : 1 + NONCE_LENGTH] for blob in blobs}

    assert len(nonces) == len(blobs)
    assert len(wrap_nonces) == len(blobs)


def test_ciphertext_length_hides_password_length() -> None:
    """Длина GCM равна длине открытого текста: без набивки дамп БД выдавал бы длину пароля."""
    short = encrypt_credentials({"password": "a"}, account_id=ACCOUNT, keyring=KEYRING_V1)
    longer = encrypt_credentials({"password": "a" * 20}, account_id=ACCOUNT, keyring=KEYRING_V1)

    assert len(short.ciphertext) == len(longer.ciphertext)


def test_blob_layout_is_stable() -> None:
    """Раскладку читает S1-05: версия формата, nonce, шифротекст с тегом."""
    stored = _encrypt()
    payload = json.dumps(CREDENTIALS, separators=(",", ":")).encode()
    padded = -(-(len(payload) + PAD_HEADER_LENGTH) // PAD_BLOCK) * PAD_BLOCK

    assert stored.ciphertext[0] == FORMAT_VERSION
    assert len(stored.ciphertext) == 1 + NONCE_LENGTH + padded + TAG_LENGTH
    assert stored.wrapped_data_key[0] == FORMAT_VERSION
    assert len(stored.wrapped_data_key) == 1 + NONCE_LENGTH + 32 + TAG_LENGTH


# --- отказы -------------------------------------------------------------------------------


@pytest.mark.parametrize("index", DAMAGE_POSITIONS, ids=DAMAGE_IDS)
def test_flipped_byte_of_ciphertext_is_rejected(index: int) -> None:
    """Порча любого байта — ошибка аутентификации, а не мусор на выходе."""
    stored = _encrypt()

    with pytest.raises(CredentialsDecryptionError):
        _decrypt(stored._replace(ciphertext=_flip(stored.ciphertext, index)))


@pytest.mark.parametrize("index", DAMAGE_POSITIONS, ids=DAMAGE_IDS)
def test_flipped_byte_of_wrapped_key_is_rejected(index: int) -> None:
    stored = _encrypt()

    with pytest.raises(CredentialsDecryptionError):
        _decrypt(stored._replace(wrapped_data_key=_flip(stored.wrapped_data_key, index)))


@pytest.mark.parametrize("truncated", [b"", b"\x01", None], ids=["пусто", "обрывок", "без байта"])
def test_short_ciphertext_is_rejected(truncated: bytes | None) -> None:
    stored = _encrypt()
    blob = stored.ciphertext[:-1] if truncated is None else truncated

    with pytest.raises(CredentialsDecryptionError):
        _decrypt(stored._replace(ciphertext=blob))


@pytest.mark.parametrize("truncated", [b"", b"\x01", None], ids=["пусто", "обрывок", "без байта"])
def test_short_wrapped_key_is_rejected(truncated: bytes | None) -> None:
    stored = _encrypt()
    blob = stored.wrapped_data_key[:-1] if truncated is None else truncated

    with pytest.raises(CredentialsDecryptionError):
        _decrypt(stored._replace(wrapped_data_key=blob))


def test_ciphertext_of_another_account_is_rejected() -> None:
    """AAD привязывает шифротекст к счёту: переставить строку в чужой счёт нельзя."""
    victim = _encrypt(ACCOUNT)
    attacker = _encrypt(OTHER_ACCOUNT)

    with pytest.raises(CredentialsDecryptionError):
        _decrypt(victim._replace(ciphertext=attacker.ciphertext))


def test_wrapped_key_of_another_account_is_rejected() -> None:
    victim = _encrypt(ACCOUNT)
    attacker = _encrypt(OTHER_ACCOUNT)

    with pytest.raises(CredentialsDecryptionError):
        _decrypt(victim._replace(wrapped_data_key=attacker.wrapped_data_key))


def test_whole_row_of_another_account_is_rejected() -> None:
    """Подмена обоих блобов сразу — тоже: AAD стоит на каждом слое."""
    attacker = _encrypt(OTHER_ACCOUNT)

    with pytest.raises(CredentialsDecryptionError):
        _decrypt(attacker, account_id=ACCOUNT)


def test_unknown_format_version_is_rejected() -> None:
    stored = _encrypt()
    blob = bytearray(stored.ciphertext)
    blob[0] = FORMAT_VERSION + 1

    with pytest.raises(CredentialsDecryptionError):
        _decrypt(stored._replace(ciphertext=bytes(blob)))


def test_unknown_key_is_rejected() -> None:
    with pytest.raises(CredentialsDecryptionError):
        _decrypt(_encrypt(), keyring=KEYRING_V2)


@pytest.mark.parametrize(
    "payload",
    [b"[1, 2]", b'{"password": 1}', b"\xff\xfe not json", b"", b"null"],
    ids=["список", "не-строка", "битый utf-8", "пусто", "null"],
)
def test_payload_that_is_not_a_string_map_is_rejected(payload: bytes) -> None:
    """Открытый текст расшифровался, но не является объектом строк — наружу тот же отказ.

    Шифротекст собирается настоящим `data_key` строки: иначе сработал бы тег, и ветка
    разбора JSON осталась бы непроверенной.
    """
    stored = _encrypt()
    data_key, _ = _unwrap_data_key(stored.wrapped_data_key, 1, ACCOUNT, KEYRING_V1)
    forged = _seal(data_key, _pad(payload), _aad(_AAD_CREDENTIALS, ACCOUNT))

    with pytest.raises(CredentialsDecryptionError):
        _decrypt(stored._replace(ciphertext=forged))


def test_every_failure_reports_the_same_text() -> None:
    """По тексту ошибки не должно быть видно, что именно не сошлось."""
    stored = _encrypt()
    cases: list[Callable[[], object]] = [
        lambda: _decrypt(stored._replace(ciphertext=_flip(stored.ciphertext, -1))),
        lambda: _decrypt(stored._replace(wrapped_data_key=b"")),
        lambda: _decrypt(stored, account_id=OTHER_ACCOUNT),
        lambda: _decrypt(stored, keyring=KEYRING_V2),
    ]

    messages = set()
    for case in cases:
        with pytest.raises(CredentialsDecryptionError) as excinfo:
            case()
        messages.add(str(excinfo.value))

    assert messages == {DECRYPTION_FAILED}


# --- версии ключа и ротация ----------------------------------------------------------------


def test_previous_key_still_reads_rows_during_rotation() -> None:
    """Пока ротация не закончена, в таблице обе версии — читать нужно уметь обе."""
    old = _encrypt()
    new = encrypt_credentials(CREDENTIALS, account_id=ACCOUNT, keyring=KEYRING_ROTATING)

    assert _decrypt(old, keyring=KEYRING_ROTATING) == CREDENTIALS
    assert _decrypt(new, keyring=KEYRING_ROTATING) == CREDENTIALS
    assert new.key_version == 2


def test_stale_key_version_column_still_decrypts(capsys: pytest.CaptureFixture[str]) -> None:
    """Оператор сменил MASTER_KEY, не подняв версию: строка читается, расхождение — в лог."""
    configure_logging()
    stored = encrypt_credentials(CREDENTIALS, account_id=ACCOUNT, keyring=KEYRING_ROTATING)

    decrypted = _decrypt(stored._replace(key_version=1), keyring=KEYRING_ROTATING)

    output = capsys.readouterr().out
    assert decrypted == CREDENTIALS
    assert "credentials.key_version_mismatch" in output
    assert PASSWORD not in output


def test_rewrap_changes_only_the_wrapper() -> None:
    """Смысл envelope: ротация трогает обёртку, шифротекст остаётся байт в байт."""
    stored = _encrypt()

    fresh = rewrap_data_key(
        stored.wrapped_data_key, stored.key_version, account_id=ACCOUNT, keyring=KEYRING_ROTATING
    )

    assert fresh.key_version == 2
    assert fresh.wrapped_data_key != stored.wrapped_data_key
    # Строка после ротации читается уже одним новым ключом, без предыдущего.
    rotated = EncryptedCredentials(stored.ciphertext, fresh.wrapped_data_key, fresh.key_version)
    assert _decrypt(rotated, keyring=KEYRING_V2) == CREDENTIALS


def test_rewrap_is_a_no_op_on_current_version() -> None:
    """Повторный прогон ротации не переписывает уже перешифрованные строки."""
    stored = encrypt_credentials(CREDENTIALS, account_id=ACCOUNT, keyring=KEYRING_ROTATING)

    fresh = rewrap_data_key(
        stored.wrapped_data_key, stored.key_version, account_id=ACCOUNT, keyring=KEYRING_ROTATING
    )

    assert fresh == (stored.wrapped_data_key, stored.key_version)


def test_rewrap_of_another_account_is_rejected() -> None:
    stored = _encrypt(OTHER_ACCOUNT)

    with pytest.raises(CredentialsDecryptionError):
        rewrap_data_key(
            stored.wrapped_data_key,
            stored.key_version,
            account_id=ACCOUNT,
            keyring=KEYRING_ROTATING,
        )


# --- ключи из окружения --------------------------------------------------------------------


def test_parse_master_key_accepts_base64_variants() -> None:
    material = bytes(range(32))
    standard = base64.b64encode(material).decode()
    urlsafe = base64.urlsafe_b64encode(material).decode().rstrip("=")

    assert parse_master_key(f"  {standard}\n", variable="MASTER_KEY") == material
    assert parse_master_key(urlsafe, variable="MASTER_KEY") == material


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "не-base64!",
        base64.b64encode(b"korotkiy").decode(),
        base64.b64encode(bytes(33)).decode(),
    ],
    ids=["пусто", "мусор", "короткий", "длинный"],
)
def test_parse_master_key_rejects_bad_values(raw: str) -> None:
    with pytest.raises(CredentialsKeyError) as excinfo:
        parse_master_key(raw, variable="MASTER_KEY")

    message = str(excinfo.value)
    assert "MASTER_KEY" in message
    # Значение ключа в сообщение не попадает даже частично.
    assert raw == "" or raw not in message


def _settings(
    *,
    key_version: int = 2,
    previous: str | None = None,
) -> Settings:
    return Settings(
        app_env="local",
        master_key=SecretStr(base64.b64encode(KEY_V2).decode()),
        master_key_version=key_version,
        master_key_previous=SecretStr(
            base64.b64encode(KEY_V1).decode() if previous is None else previous
        ),
    )


def test_keyring_from_settings_reads_both_keys() -> None:
    keyring = master_keyring(_settings())

    assert keyring.current == MasterKey(2, KEY_V2)
    assert keyring.previous == MasterKey(1, KEY_V1)


def test_keyring_without_previous_key() -> None:
    keyring = master_keyring(_settings(key_version=1, previous=""))

    assert keyring.previous is None
    assert keyring.current == MasterKey(1, KEY_V2)


def test_keyring_rejects_previous_key_at_version_one() -> None:
    with pytest.raises(CredentialsKeyError):
        master_keyring(_settings(key_version=1))


def test_keyring_rejects_previous_equal_to_current() -> None:
    with pytest.raises(CredentialsKeyError):
        master_keyring(_settings(previous=base64.b64encode(KEY_V2).decode()))


# --- ничего из открытого текста в логах -----------------------------------------------------


def test_key_material_never_reaches_repr() -> None:
    """repr объекта уезжает и в traceback, и в лог через `scrub_unserializable`."""
    keyring = MasterKeyring(current=MasterKey(2, KEY_V2), previous=MasterKey(1, KEY_V1))

    assert str(KEY_V2) not in repr(keyring)
    assert repr(keyring.current) == "MasterKey(version=2)"


def test_master_key_value_is_scrubbed_from_logs(capsys: pytest.CaptureFixture[str]) -> None:
    settings = _settings()
    configure_logging(secret_values=settings.scrubbable_secret_values())

    get_logger("test").info(
        "probe",
        master_key=settings.master_key.get_secret_value(),
        note=f"ключ={settings.master_key_previous.get_secret_value()}",
    )

    output = capsys.readouterr().out
    assert settings.master_key.get_secret_value() not in output
    assert settings.master_key_previous.get_secret_value() not in output
    assert REDACTED in output


@pytest.mark.parametrize("wrong_account", [False, True], ids=["битый байт", "чужой счёт"])
def test_failed_decryption_leaks_nothing_through_traceback(
    wrong_account: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    """Путь ошибки: traceback печатается целиком, и в нём нет ни пароля, ни ключа.

    `from None` обрывает цепочку исключений cryptography — иначе в traceback приезжает
    `InvalidTag` и с ним рамка кадра, показывающая, на каком слое не сошлось.
    """
    configure_logging(secret_values=[base64.b64encode(KEY_V1).decode()])
    stored = _encrypt()
    damaged = stored._replace(ciphertext=_flip(stored.ciphertext, -1))

    try:
        if wrong_account:
            _decrypt(stored, account_id=OTHER_ACCOUNT)
        else:
            _decrypt(damaged)
    except CredentialsDecryptionError:
        get_logger("test").exception("api.unhandled_exception")

    output = capsys.readouterr().out
    assert PASSWORD not in output
    assert "InvalidTag" not in output
    assert DECRYPTION_FAILED in output


def test_success_path_logs_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    """Успешный путь не логирует вовсе — ни пароля, ни блобов, ни ключа."""
    configure_logging()

    stored = _encrypt()
    assert _decrypt(stored) == CREDENTIALS

    assert capsys.readouterr().out == ""
