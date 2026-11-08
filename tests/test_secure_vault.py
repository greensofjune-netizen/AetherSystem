import pytest

pytest.importorskip("cryptography.fernet")

from cryptography.fernet import InvalidToken

from aether_engine.secure_vault import JesterShieldVault


def test_vault_encrypts_and_decrypts_with_matching_token():
    vault = JesterShieldVault(access_token="valid-demo-token")
    encrypted = vault.secure_data("secret payload")

    assert encrypted != b"secret payload"
    assert vault.access_vault(encrypted, "valid-demo-token") == "secret payload"


def test_vault_rejects_invalid_token_and_runs_jester_response(capsys):
    vault = JesterShieldVault(access_token="valid-demo-token")
    encrypted = vault.secure_data("secret payload")

    with pytest.raises(PermissionError, match="Access denied"):
        vault.access_vault(encrypted, "wrong-token")

    output = capsys.readouterr().out
    assert "Unauthorized vault access attempt" in output
    assert output.count("[Jester Node") == 6


def test_vault_rejects_empty_or_non_ascii_configured_token():
    with pytest.raises(ValueError, match="access_token"):
        JesterShieldVault(access_token="")
    with pytest.raises(ValueError, match="access_token"):
        JesterShieldVault(access_token="tökén")


def test_vault_rejects_payload_encrypted_with_another_key():
    first_vault = JesterShieldVault(access_token="shared-token")
    second_vault = JesterShieldVault(access_token="shared-token")
    encrypted = first_vault.secure_data("secret payload")

    with pytest.raises(InvalidToken):
        second_vault.access_vault(encrypted, "shared-token")
