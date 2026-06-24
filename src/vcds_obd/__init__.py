"""vcds_obd — live ELM327 OBD-II capture that round-trips through vcds_core.

A generic ELM327 only exposes the standard OBD-II PIDs and is BLIND to the
VAG-specific channels VCDS reads. USB adapters are strongly preferred over
Bluetooth clones, which drop samples. An OBDeleven dongle is locked to its own
app and cannot be used here as a generic serial adapter.
"""
