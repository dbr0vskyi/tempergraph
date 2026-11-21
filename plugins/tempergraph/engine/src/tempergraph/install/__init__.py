"""First install of the engine (UPD §2.7): the bootstrap the plugin's launcher runs, the engine environment,
the shim and the `PATH` block, and the self-check.

Like the updater, this package loads none of the engine's compiled libraries: its modules import the
standard library and the stdlib-only engine modules in :data:`BOOTSTRAP_IMPORTS` (a source-scan test pins it).
"""

BOOTSTRAP_IMPORTS = (
    "tempergraph.constants", "tempergraph.docs", "tempergraph.git", "tempergraph.store.layout",
    "tempergraph.security.launch", "tempergraph.release", "tempergraph.install", "tempergraph.store.migrate",
)
