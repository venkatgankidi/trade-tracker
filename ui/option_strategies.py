"""Option strategy configuration for Level 1, 3, and 4 options."""

STRATEGY_CONFIG = {
    # ── Level 1: Single-Leg ──────────────────────────────────────────
    "call": {
        "level": 1,
        "default_transaction": "debit",
        "legs": [{"leg_type": "call", "side": "buy", "label": "Long Call"}],
    },
    "put": {
        "level": 1,
        "default_transaction": "debit",
        "legs": [{"leg_type": "put", "side": "buy", "label": "Long Put"}],
    },
    "cash secured put": {
        "level": 1,
        "default_transaction": "credit",
        "legs": [{"leg_type": "put", "side": "sell", "label": "Short Put"}],
    },
    "covered call": {
        "level": 1,
        "default_transaction": "credit",
        "legs": [{"leg_type": "call", "side": "sell", "label": "Short Call"}],
    },
    "naked call": {
        "level": 1,
        "default_transaction": "credit",
        "legs": [{"leg_type": "call", "side": "sell", "label": "Naked Call"}],
    },
    "naked put": {
        "level": 1,
        "default_transaction": "credit",
        "legs": [{"leg_type": "put", "side": "sell", "label": "Naked Put"}],
    },

    # ── Level 3: Vertical Spreads (2 legs) ───────────────────────────
    "bull call spread": {
        "level": 3,
        "default_transaction": "debit",
        "legs": [
            {"leg_type": "call", "side": "buy", "label": "Long Call (Lower Strike)"},
            {"leg_type": "call", "side": "sell", "label": "Short Call (Higher Strike)"},
        ],
    },
    "bear call spread": {
        "level": 3,
        "default_transaction": "credit",
        "legs": [
            {"leg_type": "call", "side": "sell", "label": "Short Call (Lower Strike)"},
            {"leg_type": "call", "side": "buy", "label": "Long Call (Higher Strike)"},
        ],
    },
    "bull put spread": {
        "level": 3,
        "default_transaction": "credit",
        "legs": [
            {"leg_type": "put", "side": "sell", "label": "Short Put (Higher Strike)"},
            {"leg_type": "put", "side": "buy", "label": "Long Put (Lower Strike)"},
        ],
    },
    "bear put spread": {
        "level": 3,
        "default_transaction": "debit",
        "legs": [
            {"leg_type": "put", "side": "buy", "label": "Long Put (Higher Strike)"},
            {"leg_type": "put", "side": "sell", "label": "Short Put (Lower Strike)"},
        ],
    },

    # ── Level 4: Advanced Multi-Leg ──────────────────────────────────
    "iron condor": {
        "level": 4,
        "default_transaction": "credit",
        "legs": [
            {"leg_type": "put", "side": "buy", "label": "Long Put (Lowest Strike)"},
            {"leg_type": "put", "side": "sell", "label": "Short Put"},
            {"leg_type": "call", "side": "sell", "label": "Short Call"},
            {"leg_type": "call", "side": "buy", "label": "Long Call (Highest Strike)"},
        ],
    },
    "iron butterfly": {
        "level": 4,
        "default_transaction": "credit",
        "legs": [
            {"leg_type": "put", "side": "buy", "label": "Long Put (Lower Strike)"},
            {"leg_type": "put", "side": "sell", "label": "Short Put (ATM)"},
            {"leg_type": "call", "side": "sell", "label": "Short Call (ATM)"},
            {"leg_type": "call", "side": "buy", "label": "Long Call (Higher Strike)"},
        ],
    },
    "long straddle": {
        "level": 4,
        "default_transaction": "debit",
        "legs": [
            {"leg_type": "call", "side": "buy", "label": "Long Call"},
            {"leg_type": "put", "side": "buy", "label": "Long Put"},
        ],
    },
    "short straddle": {
        "level": 4,
        "default_transaction": "credit",
        "legs": [
            {"leg_type": "call", "side": "sell", "label": "Short Call"},
            {"leg_type": "put", "side": "sell", "label": "Short Put"},
        ],
    },
    "long strangle": {
        "level": 4,
        "default_transaction": "debit",
        "legs": [
            {"leg_type": "call", "side": "buy", "label": "Long Call (Higher Strike)"},
            {"leg_type": "put", "side": "buy", "label": "Long Put (Lower Strike)"},
        ],
    },
    "short strangle": {
        "level": 4,
        "default_transaction": "credit",
        "legs": [
            {"leg_type": "call", "side": "sell", "label": "Short Call (Higher Strike)"},
            {"leg_type": "put", "side": "sell", "label": "Short Put (Lower Strike)"},
        ],
    },
}


def get_strategy_names():
    """Return all strategy names."""
    return list(STRATEGY_CONFIG.keys())


def get_strategy_level(strategy):
    """Return the option level for a strategy."""
    config = STRATEGY_CONFIG.get(strategy.lower())
    return config["level"] if config else 1


def get_strategy_legs(strategy):
    """Return the leg templates for a strategy."""
    config = STRATEGY_CONFIG.get(strategy.lower())
    return config["legs"] if config else []


def is_multi_leg(strategy):
    """Check if a strategy has multiple legs."""
    return get_strategy_level(strategy) >= 3
