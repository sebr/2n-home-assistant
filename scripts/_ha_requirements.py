"""
Print the pip requirements of the Home Assistant integrations used by config/.

Walks the dependency closure of the domains named in configuration.yaml
(plus the ones Home Assistant always loads) so they can be installed into
the venv up front. That lets scripts/develop pass --skip-pip and boot fast.
"""

import json
import sys
from pathlib import Path

from homeassistant import bootstrap, components
from homeassistant.const import BASE_PLATFORMS

COMPONENTS = Path(components.__file__).parent
# Home Assistant sets these up on every boot, whatever configuration.yaml says.
# Reading them from its bootstrap module keeps the list in step with the
# installed version as new platforms (e.g. infrared) appear.
ALWAYS_LOADED = (
    bootstrap.CORE_INTEGRATIONS
    | bootstrap.LOGGING_AND_HTTP_DEPS_INTEGRATIONS
    | bootstrap.FRONTEND_INTEGRATIONS
    | bootstrap.DEFAULT_INTEGRATIONS
    | BASE_PLATFORMS
)
DOMAINS = set(sys.argv[1:]) | ALWAYS_LOADED

seen: set[str] = set()
requirements: set[str] = set()
queue = list(DOMAINS)
while queue:
    domain = queue.pop()
    if domain in seen:
        continue
    seen.add(domain)
    manifest = COMPONENTS / domain / "manifest.json"
    if not manifest.exists():
        continue
    data = json.loads(manifest.read_text())
    requirements.update(data.get("requirements", []))
    queue.extend(data.get("dependencies", []))
    queue.extend(data.get("after_dependencies", []))

print("\n".join(sorted(requirements)))
