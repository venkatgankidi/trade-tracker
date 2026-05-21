"""Option strategy configuration for Level 1, 2, 3, and 4 options based on Webull."""

STRATEGY_CONFIG = {
    # ── Level 1: Covered & Cash-Secured ──────────────────────────────────────────
    "covered call": {
        "level": 1,
        "default_transaction": "credit",
        "legs": [{"leg_type": "call", "side": "sell", "label": "Short Call"}],
    },
    "buy-write": {
        "level": 1,
        "default_transaction": "credit",
        "legs": [{"leg_type": "call", "side": "sell", "label": "Short Call"}],
    },
    "cash secured put": {
        "level": 1,
        "default_transaction": "credit",
        "legs": [{"leg_type": "put", "side": "sell", "label": "Short Put"}],
    },

    # ── Level 2: Long & Protective / Collars ─────────────────────────────────────
    "call": {  # Keep "call" for backward compatibility
        "level": 2,
        "default_transaction": "debit",
        "legs": [{"leg_type": "call", "side": "buy", "label": "Long Call"}],
    },
    "put": {  # Keep "put" for backward compatibility
        "level": 2,
        "default_transaction": "debit",
        "legs": [{"leg_type": "put", "side": "buy", "label": "Long Put"}],
    },
    "long call": {
        "level": 2,
        "default_transaction": "debit",
        "legs": [{"leg_type": "call", "side": "buy", "label": "Long Call"}],
    },
    "long put": {
        "level": 2,
        "default_transaction": "debit",
        "legs": [{"leg_type": "put", "side": "buy", "label": "Long Put"}],
    },
    "collar": {
        "level": 2,
        "default_transaction": "debit",
        "legs": [
            {"leg_type": "put", "side": "buy", "label": "Long Put (Lower Strike)"},
            {"leg_type": "call", "side": "sell", "label": "Short Call (Higher Strike)"},
        ],
    },
    "protective put": {
        "level": 2,
        "default_transaction": "debit",
        "legs": [{"leg_type": "put", "side": "buy", "label": "Long Put"}],
    },
    "protective call": {
        "level": 2,
        "default_transaction": "debit",
        "legs": [{"leg_type": "call", "side": "buy", "label": "Long Call"}],
    },
    "covered put": {
        "level": 2,
        "default_transaction": "credit",
        "legs": [{"leg_type": "put", "side": "sell", "label": "Short Put"}],
    },
    "long straddle": {
        "level": 2,
        "default_transaction": "debit",
        "legs": [
            {"leg_type": "call", "side": "buy", "label": "Long Call"},
            {"leg_type": "put", "side": "buy", "label": "Long Put"},
        ],
    },
    "long strangle": {
        "level": 2,
        "default_transaction": "debit",
        "legs": [
            {"leg_type": "call", "side": "buy", "label": "Long Call (Higher Strike)"},
            {"leg_type": "put", "side": "buy", "label": "Long Put (Lower Strike)"},
        ],
    },

    # ── Level 3: Spreads & Butterflies / Condors ──────────────────────────────────
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
    "credit spread": {
        "level": 3,
        "default_transaction": "credit",
        "legs": [
            {"leg_type": "call", "side": "sell", "label": "Short Leg"},
            {"leg_type": "call", "side": "buy", "label": "Long Leg (Hedge)"},
        ],
    },
    "debit spread": {
        "level": 3,
        "default_transaction": "debit",
        "legs": [
            {"leg_type": "call", "side": "buy", "label": "Long Leg"},
            {"leg_type": "call", "side": "sell", "label": "Short Leg (Hedge)"},
        ],
    },
    "long butterfly": {
        "level": 3,
        "default_transaction": "debit",
        "legs": [
            {"leg_type": "call", "side": "buy", "label": "Long Call (Lower Strike)"},
            {"leg_type": "call", "side": "sell", "label": "Short Call (Middle Strike) x2"},
            {"leg_type": "call", "side": "buy", "label": "Long Call (Higher Strike)"},
        ],
    },
    "short butterfly": {
        "level": 3,
        "default_transaction": "credit",
        "legs": [
            {"leg_type": "call", "side": "sell", "label": "Short Call (Lower Strike)"},
            {"leg_type": "call", "side": "buy", "label": "Long Call (Middle Strike) x2"},
            {"leg_type": "call", "side": "sell", "label": "Short Call (Higher Strike)"},
        ],
    },
    "long condor": {
        "level": 3,
        "default_transaction": "debit",
        "legs": [
            {"leg_type": "call", "side": "buy", "label": "Long Call (Lowest Strike)"},
            {"leg_type": "call", "side": "sell", "label": "Short Call (Lower Middle Strike)"},
            {"leg_type": "call", "side": "sell", "label": "Short Call (Higher Middle Strike)"},
            {"leg_type": "call", "side": "buy", "label": "Long Call (Highest Strike)"},
        ],
    },
    "short condor": {
        "level": 3,
        "default_transaction": "credit",
        "legs": [
            {"leg_type": "call", "side": "sell", "label": "Short Call (Lowest Strike)"},
            {"leg_type": "call", "side": "buy", "label": "Long Call (Lower Middle Strike)"},
            {"leg_type": "call", "side": "buy", "label": "Long Call (Higher Middle Strike)"},
            {"leg_type": "call", "side": "sell", "label": "Short Call (Highest Strike)"},
        ],
    },
    "iron condor": {
        "level": 3,
        "default_transaction": "credit",
        "legs": [
            {"leg_type": "put", "side": "buy", "label": "Long Put (Lowest Strike)"},
            {"leg_type": "put", "side": "sell", "label": "Short Put"},
            {"leg_type": "call", "side": "sell", "label": "Short Call"},
            {"leg_type": "call", "side": "buy", "label": "Long Call (Highest Strike)"},
        ],
    },
    "iron butterfly": {
        "level": 3,
        "default_transaction": "credit",
        "legs": [
            {"leg_type": "put", "side": "buy", "label": "Long Put (Lower Strike)"},
            {"leg_type": "put", "side": "sell", "label": "Short Put (ATM)"},
            {"leg_type": "call", "side": "sell", "label": "Short Call (ATM)"},
            {"leg_type": "call", "side": "buy", "label": "Long Call (Higher Strike)"},
        ],
    },
    "back ratio call spread": {
        "level": 3,
        "default_transaction": "debit",
        "legs": [
            {"leg_type": "call", "side": "sell", "label": "Short Call (Lower Strike)"},
            {"leg_type": "call", "side": "buy", "label": "Long Call (Higher Strike) x2"},
        ],
    },
    "back ratio put spread": {
        "level": 3,
        "default_transaction": "debit",
        "legs": [
            {"leg_type": "put", "side": "sell", "label": "Short Put (Higher Strike)"},
            {"leg_type": "put", "side": "buy", "label": "Long Put (Lower Strike) x2"},
        ],
    },

    # ── Level 4: Naked Options & Ratios ──────────────────────────────────────────
    "naked call": {
        "level": 4,
        "default_transaction": "credit",
        "legs": [{"leg_type": "call", "side": "sell", "label": "Naked Call"}],
    },
    "naked put": {
        "level": 4,
        "default_transaction": "credit",
        "legs": [{"leg_type": "put", "side": "sell", "label": "Naked Put"}],
    },
    "naked index call": {
        "level": 4,
        "default_transaction": "credit",
        "legs": [{"leg_type": "call", "side": "sell", "label": "Naked Index Call"}],
    },
    "naked index put": {
        "level": 4,
        "default_transaction": "credit",
        "legs": [{"leg_type": "put", "side": "sell", "label": "Naked Index Put"}],
    },
    "front ratio call spread": {
        "level": 4,
        "default_transaction": "credit",
        "legs": [
            {"leg_type": "call", "side": "buy", "label": "Long Call (Lower Strike)"},
            {"leg_type": "call", "side": "sell", "label": "Short Call (Higher Strike) x2"},
        ],
    },
    "front ratio put spread": {
        "level": 4,
        "default_transaction": "credit",
        "legs": [
            {"leg_type": "put", "side": "buy", "label": "Long Put (Higher Strike)"},
            {"leg_type": "put", "side": "sell", "label": "Short Put (Lower Strike) x2"},
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
    legs = get_strategy_legs(strategy)
    return len(legs) > 1

