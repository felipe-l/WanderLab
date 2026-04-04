"""Discord embed formatter for opportunity briefs."""

VERDICT_COLORS = {
    "build": 0x2ECC71,   # green
    "watch": 0xF39C12,   # orange
    "skip": 0xE74C3C,    # red
}

VERDICT_EMOJI = {
    "build": "🟢 BUILD",
    "watch": "🟡 WATCH",
    "skip": "🔴 SKIP",
}

FIELD_LIMIT = 1024  # Discord field value character limit
TITLE_LIMIT = 256   # Discord embed title character limit


def _truncate(value: str | None, limit: int = FIELD_LIMIT) -> str:
    """Truncate a string to Discord's field limit. Never return empty string."""
    if not value:
        return "N/A"
    value = str(value)
    if len(value) <= limit:
        return value
    return value[:limit - 3] + "..."


def _field(name: str, value: str | None, inline: bool = False) -> dict:
    return {"name": name, "value": _truncate(value), "inline": inline}


def _format_products_mentioned(products_mentioned: dict) -> str | None:
    """Format products_mentioned dict as a readable string."""
    if not products_mentioned:
        return None
    return ", ".join(f"**{p}** ({n})" for p, n in sorted(products_mentioned.items(), key=lambda x: -x[1]))


def format_brief(brief: dict) -> dict:
    """Format an opportunity brief as a Discord embed."""
    verdict = brief.get("verdict", "skip").lower()
    theme = brief.get("problem_theme", "Unknown Theme")
    products_str = _format_products_mentioned(brief.get("products_mentioned") or {})

    fields = [
        _field("Verdict", VERDICT_EMOJI.get(verdict, verdict.upper()), inline=True),
        _field("Evidence", f"{brief.get('evidence_count', 0)} complaints · Score {brief.get('avg_composite_score', 0):.2f}", inline=True),
        _field("Build Complexity", brief.get("build_complexity", "Unknown"), inline=True),
        _field("Product Concept", brief.get("product_concept")),
        _field("Buyer", brief.get("buyer_profile")),
        _field("Why Incumbents Fail", brief.get("why_incumbents_fail")),
        _field("Wedge", brief.get("wedge")),
        _field("Rationale", brief.get("verdict_rationale")),
    ]

    if products_str:
        fields.append(_field("Seen In", products_str))

    quotes = brief.get("sample_complaints", [])
    if quotes:
        quote_text = "\n".join(f'> "{q[:200]}"' for q in quotes[:2])
        fields.append(_field("User Voices", quote_text))

    return {
        "title": _truncate(theme, TITLE_LIMIT),
        "color": VERDICT_COLORS.get(verdict, 0x95A5A6),
        "fields": fields,
        "footer": {"text": "WanderLab Pipeline · Analyst"},
    }
