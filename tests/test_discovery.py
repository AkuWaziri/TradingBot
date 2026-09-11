from discovery import PUMP_PROGRAM_ID, _extract_pump_create_mints, _merge, DiscoveredMint


def test_extracts_pump_create_mint_from_parsed_instruction():
    mint = "Mint111111111111111111111111111111111111111"
    transaction = {
        "transaction": {
            "message": {
                "instructions": [
                    {
                        "programId": PUMP_PROGRAM_ID,
                        "parsed": {"type": "createV2"},
                        "accounts": [mint, "authority", "curve"],
                    }
                ]
            }
        },
        "meta": {"logMessages": []},
    }

    assert _extract_pump_create_mints(transaction) == [mint]


def test_ignores_pump_buy_instruction():
    transaction = {
        "transaction": {
            "message": {
                "instructions": [
                    {
                        "programId": PUMP_PROGRAM_ID,
                        "parsed": {"type": "buyV2"},
                        "accounts": ["Mint111111111111111111111111111111111111111"],
                    }
                ]
            }
        },
        "meta": {"logMessages": []},
    }

    assert _extract_pump_create_mints(transaction) == []


def test_merge_deduplicates_mints_and_preserves_sources():
    mint = "Mint111111111111111111111111111111111111111"
    other = "Other11111111111111111111111111111111111111"

    result = _merge(
        [
            DiscoveredMint(mint, ("pump_fun_onchain",)),
            DiscoveredMint(mint, ("dexscreener",)),
            DiscoveredMint(other, ("dexscreener",)),
        ],
        30,
    )

    assert result == [
        DiscoveredMint(mint, ("dexscreener", "pump_fun_onchain")),
        DiscoveredMint(other, ("dexscreener",)),
    ]
