"""Test Analyst's Discord embed formatter — no API calls needed.

Usage:
    cd tests
    python test_analyst_formatter.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.analyst.formatter import format_product_brief, format_unmet_need_brief, format_weak_signals

FIELD_LIMIT = 1024
TITLE_LIMIT = 256


def check_embed_limits(embed: dict, label: str):
    errors = []

    title = embed.get("title", "")
    if len(title) > TITLE_LIMIT:
        errors.append(f"  ✗ title too long: {len(title)} chars")

    for field in embed.get("fields", []):
        name = field.get("name", "")
        value = field.get("value", "")
        if len(name) > 256:
            errors.append(f"  ✗ field name too long ({len(name)}): {name[:50]}")
        if len(value) > FIELD_LIMIT:
            errors.append(f"  ✗ field value too long ({len(value)}): {name}")
        if not value:
            errors.append(f"  ✗ field value is empty: {name}")

    if errors:
        print(f"\n{label} FAILED:")
        for e in errors:
            print(e)
        return False
    else:
        print(f"  ✓ {label}: all fields within Discord limits")
        return True


def test_product_brief():
    brief = {
        "product_name": "Jira",
        "problem_theme": "Performance and slow load times that kill team productivity",
        "verdict": "build",
        "evidence_count": 18,
        "avg_composite_score": 0.75,
        "build_complexity": "1 month",
        "product_concept": "An AI-native project tracker that predicts bottlenecks before they happen, automatically reprioritizes backlogs based on team velocity, and generates status updates. Built for 5-50 person startups who find Jira too slow and too complex.",
        "buyer_profile": "Engineering managers and CTOs at 10-100 person startups paying $8-20/user/month for Jira.",
        "what_incumbent_gets_wrong": "Jira was built for large enterprises and the performance reflects that — every action requires a round trip to a slow server. It optimizes for configurability over speed.",
        "wedge": "Free Jira CSV importer + a landing page targeting 'Jira alternatives' searches. First 100 users from r/projectmanagement and LinkedIn engineering communities.",
        "verdict_rationale": "Strong signal: 18 complaints, high WTP (users naming specific alternatives), and AI replaceability is real — sprint planning and status updates are exactly what LLMs are good at.",
        "sample_complaints": [
            "Our team spends more time waiting for Jira pages to load than actually working. We're evaluating Linear.",
            "Simple ticket updates take 10+ seconds. This is unacceptable for a $20/user/month tool.",
            "x" * 300,  # intentionally long to test truncation
        ],
    }
    embed = format_product_brief(brief)
    return check_embed_limits(embed, "Product brief (normal)")


def test_long_fields():
    """Test that extremely long field values are truncated correctly."""
    brief = {
        "product_name": "A" * 300,  # very long product name
        "problem_theme": "B" * 300,
        "verdict": "watch",
        "evidence_count": 5,
        "avg_composite_score": 0.55,
        "build_complexity": "3+ months",
        "product_concept": "C" * 2000,  # way over limit
        "buyer_profile": "D" * 2000,
        "what_incumbent_gets_wrong": "E" * 2000,
        "wedge": "F" * 2000,
        "verdict_rationale": "G" * 2000,
        "sample_complaints": ["H" * 500, "I" * 500],
    }
    embed = format_product_brief(brief)
    return check_embed_limits(embed, "Product brief (long fields truncation)")


def test_empty_fields():
    """Test that missing/None fields don't produce empty Discord fields."""
    brief = {
        "product_name": "Slack",
        "problem_theme": "Notification overload",
        "verdict": "skip",
        "evidence_count": 3,
        "avg_composite_score": 0.40,
        "build_complexity": None,
        "product_concept": None,
        "buyer_profile": None,
        "what_incumbent_gets_wrong": None,
        "wedge": None,
        "verdict_rationale": None,
        "sample_complaints": [],
    }
    embed = format_product_brief(brief)
    return check_embed_limits(embed, "Product brief (empty/None fields)")


def test_unmet_need():
    brief = {
        "problem_theme": "No good tool for async meeting summaries that integrate with calendar",
        "verdict": "build",
        "evidence_count": 12,
        "avg_composite_score": 0.65,
        "build_complexity": "1 month",
        "product_concept": "AI meeting summarizer that auto-joins calls, generates action items, and syncs to your project tracker.",
        "buyer_profile": "Remote-first teams of 10-50 people who live in meetings.",
        "why_no_solution_exists": "Most tools require manual recording uploads. Real-time AI joining is technically hard and privacy-sensitive.",
        "wedge": "Free for first 10 meetings, no credit card required.",
        "verdict_rationale": "Clear recurring pain, AI is a perfect fit, buyers are identifiable.",
        "sample_complaints": ["I spend 2 hours every week writing up meeting notes", "Why is there no tool that just does this automatically?"],
    }
    embed = format_unmet_need_brief(brief)
    return check_embed_limits(embed, "Unmet need brief")


def test_weak_signals():
    clusters = [
        {"product_name": "Basecamp", "problem_theme": "General complaints about Basecamp"},
        {"product_name": "Linear", "problem_theme": "Missing features"},
        {"product_name": "A" * 200, "problem_theme": "B" * 200},  # long strings
    ]
    result = format_weak_signals(clusters)
    assert len(result) <= 2000, f"Weak signals message too long: {len(result)}"
    assert "Basecamp" in result
    print("  ✓ Weak signals formatter works")
    return True


if __name__ == "__main__":
    print("Running formatter tests (no API calls)...\n")
    results = [
        test_product_brief(),
        test_long_fields(),
        test_empty_fields(),
        test_unmet_need(),
        test_weak_signals(),
    ]

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} tests passed.")
    if passed < total:
        sys.exit(1)
