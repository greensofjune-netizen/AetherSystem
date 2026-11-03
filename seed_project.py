import os


def write_if_missing(path, content):
    if os.path.exists(path):
        print(f"  [=] Preserved existing: {path}")
        return
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)
    print(f"  [+] Created: {path}")


def build_root_and_tree():
    print("\n--- Seeding Project Skeleton Layout ---")
    
    # Create the folder layout
    for folder in ["src/aether_engine", "tests"]:
        os.makedirs(folder, exist_ok=True)

    # 1. pyproject.toml package configuration
    write_if_missing("pyproject.toml", """[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "aether-engine"
version = "0.1.0"
description = "Aether Engine tracking array."
readme = "README.md"
requires-python = ">=3.11"
dependencies = ["pytest>=7.0.0"]

[project.scripts]
aether-engine = "aether_engine.cli:main"
""")

    # 2. __init__.py
    write_if_missing("src/aether_engine/__init__.py", '__version__ = "0.1.0"\n')

    # 3. historian.py
    write_if_missing("src/aether_engine/historian.py", """import time, math, uuid
class CoPilotHistorian:
    def __init__(self):
        self.registry = {}
    def drop_anchor(self, topic):
        aid = str(uuid.uuid4())[:8]
        self.registry[aid] = topic
        return aid
""")

    # 4. cli.py
    write_if_missing("src/aether_engine/cli.py", """def main():
    print("\\n📡 AETHER ENGINE CLI ACTIVE")
""")

    # 5. README.md
    write_if_missing("README.md", "# Aether Engine\n")

    # 6. Keep the local project database out of version control
    write_if_missing(
        ".gitignore",
        ".aether-engine.sqlite3*\n.aether-backups/\n.venv/\n__pycache__/\n.pytest_cache/\n*.egg-info/\n",
    )

    print("\n[✔] PROJECT SKELETON READY")

if __name__ == "__main__":
    build_root_and_tree()
