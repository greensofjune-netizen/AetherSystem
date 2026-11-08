"""AetherSystem cryptographic vault with a playful denial response."""

import random
import secrets

from cryptography.fernet import Fernet


class JesterShieldVault:
    """Encrypt string payloads and require a caller-provided access token."""

    def __init__(
        self,
        access_token: str,
        encryption_key: bytes | None = None,
    ) -> None:
        if not access_token or not access_token.isascii():
            raise ValueError("access_token must be a non-empty ASCII string")

        self._access_token = access_token
        self._secret_key = (
            Fernet.generate_key() if encryption_key is None else encryption_key
        )
        self._cipher = Fernet(self._secret_key)
        self._jests = [
            {"q": "Why can't you trust an atom?", "a": "Because they make up everything!"},
            {
                "q": "What did the physicist say when stuck on the singular loop bounce?",
                "a": "Go big or go home!",
            },
            {
                "q": "How does a quantum computer tell a joke?",
                "a": "In a superposition of funny and not funny until you observe it.",
            },
            {"q": "Schrödinger's cat walks into a bar...", "a": "...and doesn't."},
            {
                "q": "Why are quantum physicists bad lovers?",
                "a": "Because when they find the position, they lose the momentum.",
            },
            {
                "q": "What do you call a physicist who struggles with sloppy handwriting?",
                "a": "A master of continuous transformations!",
            },
        ]

    def secure_data(self, clear_payload: str) -> bytes:
        """Encrypt a UTF-8 string using this vault's Fernet key."""
        if not isinstance(clear_payload, str):
            raise TypeError("clear_payload must be a string")
        return self._cipher.encrypt(clear_payload.encode("utf-8"))

    def access_vault(self, encrypted_payload: bytes, access_token: str) -> str:
        """Decrypt a payload after authenticating the supplied access token."""
        if (
            not isinstance(access_token, str)
            or not access_token.isascii()
            or not secrets.compare_digest(access_token, self._access_token)
        ):
            print("[SECURITY WARNING] Unauthorized vault access attempt.")
            for index in range(3):
                jest = random.choice(self._jests)
                print(f"[Jester Node {index + 1}] RIDDLE: {jest['q']}")
                print(f"[Jester Node {index + 1}] ANSWER: {jest['a']}")
            raise PermissionError("Access denied. Vault boundaries protected.")

        return self._cipher.decrypt(encrypted_payload).decode("utf-8")


if __name__ == "__main__":
    demo_token = secrets.token_urlsafe(32)
    vault = JesterShieldVault(access_token=demo_token)
    secret_blueprint = "Formula 08: Micro Loop Gauge Connected Successfully."
    masked_bytes = vault.secure_data(secret_blueprint)

    print("[VAULT TEST] Accessing with a generated demo token:")
    print("Result:", vault.access_vault(masked_bytes, demo_token))

    try:
        print("\n[VAULT TEST] Accessing with an invalid token:")
        vault.access_vault(masked_bytes, "invalid-demo-token")
    except PermissionError as error:
        print(f"System response: {error}")
