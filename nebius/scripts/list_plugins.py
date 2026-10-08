"""Print discovered plugins with status (make plugins)."""

from api.core.plugins import load_plugins
from api.core.settings import ROOT_DIR

host = load_plugins(ROOT_DIR)
print(f"{'id':22} {'version':8} {'status':10} provides")
for st in host.statuses.values():
    status = "disabled" if not st.enabled else "healthy" if st.healthy else "ERROR"
    print(f"{st.id:22} {st.version:8} {status:10} {', '.join(st.provides)}")
    if st.error:
        print(f"{'':22} {st.error}")
