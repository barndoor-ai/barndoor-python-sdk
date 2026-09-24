# Examples

Runnable against a real Barndoor organization. Each one reads its credentials
from the environment and says which variables it needs.

| File | Shows |
|---|---|
| `list_mcp_servers.py` | The smallest useful call — authenticate and read |
| `machine_to_machine.py` | Client-credentials auth, refreshed for you |
| `mcp_client.py` | Connecting to MCP and listing tools |
| `connection_params.py` | MCP connection details for another framework |

```bash
pip install barndoor
BARNDOOR_API_KEY=bdai_… python list_mcp_servers.py
```

These are import-checked against the client on every regeneration, so an API
change that breaks one fails CI rather than reaching you.
