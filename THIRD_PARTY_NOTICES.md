# Third-party materials

The root [MIT license](./LICENSE) applies to original Aether Engine material.
It does not replace the licenses of dependencies, downloaded model weights,
or third-party materials.

## Modern Web Guidance

The developer guidance under `.agents/skills/modern-web-guidance/` originates
from [GoogleChrome/modern-web-guidance](https://github.com/GoogleChrome/modern-web-guidance).
When installed locally, its source is recorded in `skills-lock.json`.
The upstream repository supplies
the [Apache License 2.0](https://github.com/GoogleChrome/modern-web-guidance/blob/main/LICENSE).
A copy is retained alongside the guidance. Preserve that license and any
upstream notices when redistributing the guidance; it is not relicensed as MIT.
The guidance and its installation lock file are local developer tools, excluded
from the source-and-CLI release commit and Python distributions. The retained
local license is not a bundled dependency of Aether.

## Dependencies, tools, and models

Python and JavaScript dependencies retain their own licenses. A core Aether
wheel does not bundle installed Python dependencies or model weights.
Before distributing a frozen desktop app, review and retain the licenses and
notices of every bundled dependency.

Downloaded model weights have their own terms; verify the license of the exact
model and revision before redistributing it. The local `swiftly.pkg` installer
is an external Swift tool, not Aether software, and is excluded from Python
distributions. Do not treat the Aether MIT license as permission to redistribute
third-party installers, weights, or reference content.
