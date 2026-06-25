"""Curated diagnostic-trouble-code knowledge for VAG/Audi + generic OBD-II.

Data only — no logic (see :mod:`vcds_core.knowledge`). Standard-library safe:
this is a plain Python dict so it bundles into PyInstaller with no data-file
configuration and keeps ``vcds_core`` dependency-free.

Each entry: ``description``, ``severity`` (info|low|medium|high|critical),
``system``, ``causes`` (most-likely first) and an optional ``notes`` string for
VAG-specific context. Codes are stored without the leading apostrophe VCDS uses.
"""

from __future__ import annotations

# Severity ranking used for sorting/aggregation.
SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}

# Generic OBD-II P0xxx structural subsystem hints (second digit of a P0/P2 code).
P_SUBSYSTEM = {
    "0": "Fuel & air metering / auxiliary emission controls",
    "1": "Fuel & air metering",
    "2": "Fuel & air metering (injector circuit)",
    "3": "Ignition system or misfire",
    "4": "Auxiliary emission controls",
    "5": "Vehicle speed, idle control & auxiliary inputs",
    "6": "Computer output circuit / ECU",
    "7": "Transmission",
    "8": "Transmission",
    "9": "Transmission / control modules",
}

# First-letter category for any DTC.
CODE_CATEGORY = {
    "P": "Powertrain (engine/transmission)",
    "C": "Chassis (ABS/brakes/steering)",
    "B": "Body (comfort/airbags/HVAC)",
    "U": "Network / communication (CAN bus)",
}

CODE_DB = {
    # --- Fuel trim / mixture ------------------------------------------------ #
    "P0171": {
        "description": "System Too Lean (Bank 1)",
        "severity": "medium",
        "system": "Fuel & air metering",
        "causes": ["Intake/vacuum leak", "Failing PCV valve", "Dirty/failed MAF sensor",
                   "Low fuel pressure", "Leaking injector seals"],
        "notes": "On VAG TFSI/TSI engines a torn PCV/crankcase breather is the classic cause; "
                 "watch Long Fuel Trim climbing positive at idle.",
    },
    "P0172": {
        "description": "System Too Rich (Bank 1)",
        "severity": "medium",
        "system": "Fuel & air metering",
        "causes": ["Leaking injector", "High fuel pressure", "Failed MAF", "Faulty O2 sensor",
                   "Restricted air intake"],
    },
    "P0174": {
        "description": "System Too Lean (Bank 2)",
        "severity": "medium",
        "system": "Fuel & air metering",
        "causes": ["Intake/vacuum leak", "Failing PCV valve", "Dirty/failed MAF sensor",
                   "Low fuel pressure"],
    },
    "P2279": {
        "description": "Intake Air System Leak",
        "severity": "medium",
        "system": "Fuel & air metering",
        "causes": ["Cracked intake boot", "Failed PCV/crankcase breather", "Loose intake clamp"],
        "notes": "Frequently paired with P0171 on VAG engines — check the PCV diaphragm first.",
    },
    "P0087": {
        "description": "Fuel Rail/System Pressure Too Low",
        "severity": "high",
        "system": "Fuel delivery",
        "causes": ["Weak low-pressure fuel pump", "Worn high-pressure fuel pump / cam follower",
                   "Clogged fuel filter", "Failed fuel pressure sensor"],
        "notes": "On FSI engines a worn HPFP cam follower is a known cause — inspect the follower.",
    },
    # --- MAF / MAP / intake ------------------------------------------------- #
    "P0101": {
        "description": "Mass Air Flow Circuit Range/Performance",
        "severity": "medium",
        "system": "Air metering",
        "causes": ["Dirty/contaminated MAF element", "Intake leak after the MAF", "Failed MAF"],
    },
    "P0102": {"description": "Mass Air Flow Circuit Low Input", "severity": "medium",
              "system": "Air metering", "causes": ["Failed MAF", "Wiring/connector fault"]},
    "P0103": {"description": "Mass Air Flow Circuit High Input", "severity": "medium",
              "system": "Air metering", "causes": ["Failed MAF", "Intake restriction"]},
    "P0106": {"description": "Manifold Absolute Pressure Range/Performance", "severity": "medium",
              "system": "Air metering", "causes": ["Failed MAP sensor", "Boost leak", "Vacuum leak"]},
    "P0113": {"description": "Intake Air Temperature Sensor High Input", "severity": "low",
              "system": "Air metering", "causes": ["Failed IAT sensor", "Wiring open circuit"]},
    # --- Boost / forced induction (very relevant to the 3.0T) --------------- #
    "P0234": {
        "description": "Turbo/Supercharger Overboost Condition",
        "severity": "high",
        "system": "Forced induction",
        "causes": ["Stuck wastegate", "Faulty N75 boost control valve", "Faulty boost sensor",
                   "Sticking diverter valve"],
    },
    "P0299": {
        "description": "Turbo/Supercharger Underboost",
        "severity": "high",
        "system": "Forced induction",
        "causes": ["Boost/charge-pipe leak", "Failed diverter (bypass) valve", "Faulty N75 valve",
                   "Wastegate actuator", "Cracked intercooler"],
        "notes": "Most common cause on VAG turbos is a split charge pipe or a failed diverter "
                 "valve. Compare Boost (actual) against the requested value under load.",
    },
    "P2563": {"description": "Turbo Boost Control Position Sensor Range/Performance",
              "severity": "medium", "system": "Forced induction",
              "causes": ["Wastegate actuator", "Boost position sensor", "Linkage binding"]},
    # --- Misfire / ignition ------------------------------------------------- #
    "P0300": {
        "description": "Random/Multiple Cylinder Misfire Detected",
        "severity": "high",
        "system": "Ignition / combustion",
        "causes": ["Worn spark plugs", "Failing ignition coils", "Carbon-fouled intake valves",
                   "Vacuum leak", "Low fuel pressure"],
        "notes": "On direct-injection VAG engines, carbon build-up on the intake valves is a "
                 "frequent cause of multi-cylinder misfires — consider a walnut-blast clean.",
    },
    **{
        f"P030{c}": {
            "description": f"Cylinder {c} Misfire Detected",
            "severity": "high",
            "system": "Ignition / combustion",
            "causes": ["Spark plug", "Ignition coil", "Fuel injector", "Low compression",
                       "Carbon build-up"],
            "notes": "Swap the coil/plug to the next cylinder and re-log — if the misfire follows, "
                     "the coil/plug is at fault.",
        }
        for c in range(1, 7)
    },
    "P0327": {"description": "Knock Sensor 1 Circuit Low", "severity": "medium",
              "system": "Ignition", "causes": ["Failed knock sensor", "Wiring/connector", "Loose sensor bolt"]},
    # --- Camshaft / VVT ----------------------------------------------------- #
    "P0011": {
        "description": "Camshaft Position 'A' Timing Over-Advanced (Bank 1)",
        "severity": "medium",
        "system": "Variable valve timing",
        "causes": ["Dirty oil / overdue oil change", "Failed cam adjuster (solenoid)",
                   "Stretched timing chain", "Low oil pressure"],
        "notes": "On VAG engines this often means a failing cam adjuster magnet or a stretched "
                 "timing chain — check oil condition first.",
    },
    "P0341": {"description": "Camshaft Position Sensor Range/Performance", "severity": "medium",
              "system": "Variable valve timing", "causes": ["Cam position sensor", "Timing chain stretch", "Wiring"]},
    # --- O2 / catalyst ------------------------------------------------------ #
    "P2196": {
        "description": "O2 Sensor Signal Stuck Rich (Bank 1 Sensor 1)",
        "severity": "medium",
        "system": "Fuel & air metering",
        "causes": ["Failed wideband O2 sensor", "Fuel pressure issue", "Intake leak skewing trims"],
    },
    "P0420": {"description": "Catalyst System Efficiency Below Threshold (Bank 1)", "severity": "medium",
              "system": "Emissions", "causes": ["Aged catalytic converter", "Failed rear O2 sensor",
                                                  "Exhaust leak", "Lingering misfire/rich condition"]},
    # --- Cooling ------------------------------------------------------------ #
    "P0128": {"description": "Coolant Thermostat (Below Regulating Temperature)", "severity": "low",
              "system": "Cooling", "causes": ["Stuck-open thermostat", "Failed coolant temp sensor"]},
    "P2181": {"description": "Cooling System Performance", "severity": "medium",
              "system": "Cooling", "causes": ["Thermostat", "Coolant temp sensor", "Water pump", "Low coolant"]},
    # --- Communication ------------------------------------------------------ #
    "U0101": {"description": "Lost Communication with TCM", "severity": "high",
              "system": "Network / CAN", "causes": ["CAN wiring fault", "Failed TCM", "Connector corrosion"]},
    "U0121": {"description": "Lost Communication with ABS Control Module", "severity": "high",
              "system": "Network / CAN", "causes": ["CAN wiring", "ABS module power/ground", "Connector"]},
}

# Manufacturer-specific (P1xxx) codes by brand. Generic P0xxx codes live in
# CODE_DB and are shared by every profile; these are only consulted for the
# matching vehicle profile.
BRAND_CODE_DB = {
    "ford": {
        "P1000": {"description": "OBD-II Monitor Testing Not Complete", "severity": "info",
                  "system": "Readiness", "causes": ["Drive cycle not completed since codes cleared"]},
        "P1100": {"description": "Mass Air Flow Sensor Intermittent", "severity": "medium",
                  "system": "Air metering", "causes": ["Failing MAF", "Wiring/connector", "Intake leak"]},
        "P1112": {"description": "Intake Air Temperature Sensor Intermittent", "severity": "low",
                  "system": "Air metering", "causes": ["IAT sensor", "Wiring"]},
        "P1131": {"description": "Lack of HO2S-11 Switch — Sensor Indicates Lean (Bank 1)",
                  "severity": "medium", "system": "Fuel & air metering",
                  "causes": ["Upstream O2 sensor", "Vacuum/intake leak", "Low fuel pressure", "Exhaust leak"]},
        "P1151": {"description": "Lack of HO2S-21 Switch — Sensor Indicates Lean (Bank 2)",
                  "severity": "medium", "system": "Fuel & air metering",
                  "causes": ["Upstream O2 sensor (B2)", "Vacuum/intake leak", "Low fuel pressure"]},
        "P1260": {"description": "Theft Detected — Vehicle Immobilized (PATS)", "severity": "high",
                  "system": "Anti-theft", "causes": ["Key not recognized", "PATS transceiver", "Key/IC fault"]},
        "P1289": {"description": "Cylinder Head Temperature Sensor High Input", "severity": "high",
                  "system": "Cooling", "causes": ["Overheating", "CHT sensor", "Low coolant", "Wiring"]},
        "P1450": {"description": "Unable to Bleed Up Fuel Tank Vacuum", "severity": "low",
                  "system": "Emissions (EVAP)", "causes": ["Blocked EVAP line", "Purge/vent valve", "Fuel cap"]},
        "P144A": {"description": "EVAP System Purge Vapor Line Restricted", "severity": "low",
                  "system": "Emissions (EVAP)", "causes": ["Restricted purge line", "Purge valve"]},
    },
}

# VAG known-issue knowledge keyed by a short topic, surfaced by the diagnostic engine.
KNOWN_ISSUES = {
    "carbon_buildup": "Direct-injection (FSI/TFSI) intake valves accumulate carbon, causing rough "
                      "idle, misfires and reduced power. Remedy: walnut-blast intake-valve clean.",
    "pcv_failure": "The PCV / crankcase breather diaphragm cracks with age, causing lean codes "
                   "(P0171/P2279), rough idle and a whistling vacuum leak.",
    "diverter_valve": "Turbo diverter (bypass) valves fail and cause underboost (P0299), hesitation "
                      "and loss of power. Often updated to a revised part.",
    "hpfp_cam_follower": "The high-pressure fuel pump cam follower wears through, risking low fuel "
                         "pressure (P0087) and camshaft damage — inspect periodically.",
    "timing_chain": "Early timing-chain tensioners can fail, causing a cold-start rattle and cam "
                    "timing codes (P0011/P0016). Address promptly to avoid valve damage.",
}
