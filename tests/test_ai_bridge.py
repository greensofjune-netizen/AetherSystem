import ollama


def test_local_core_connection():
    """Validates the dynamic local handshake with our custom core model."""
    print("\n[AetherSystem] Initiating secure local AI bridge test...")

    test_prompt = "System initialization handshake. Report your active protocol status."

    try:
        # Communicate directly with the local Ollama registry
        response = ollama.generate(
            model="aethersystem-core",
            prompt=test_prompt,
            options={"temperature": 0.2},
        )

        print("\n=== [AetherSystem-Core Response] ===")
        print(response["response"].strip())
        print("====================================\n")
        print("[AetherSystem] AI Bridge verified successfully.")

    except Exception as e:
        print("\n[!] Connection Failed: Ensure Ollama is running in the background.")
        print(f"Details: {str(e)}\n")


if __name__ == "__main__":
    test_local_core_connection()
