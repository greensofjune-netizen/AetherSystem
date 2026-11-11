"""Compatibility entry point for the packaged live-sync supervisor."""

import asyncio
import sys

from aether_engine import live_sync_supervisor as _implementation

if __name__ == "__main__":
    try:
        asyncio.run(_implementation.main())
    except KeyboardInterrupt:
        print("\nPipeline broken via terminal sequence. Goodbye.")
else:
    sys.modules[__name__] = _implementation
