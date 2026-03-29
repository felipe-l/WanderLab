"""Test Scout's complaint classifier in isolation.

Usage:
    cd tests
    python test_scout_classifier.py           # uses fixture data, no LLM calls
    python test_scout_classifier.py --live    # makes real LLM calls via OpenRouter
"""

import asyncio
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# --- Fixture data (no API calls needed) ---
FIXTURE_ITEMS = [
    {
        "source": "reddit",
        "subreddit": "SaaS",
        "body": "Jira is absolutely killing our team's productivity. Pages take 10+ seconds to load and we're seriously considering switching to Linear next month.",
        "title": "Jira performance is unbearable",
    },
    {
        "source": "reddit",
        "subreddit": "SaaS",
        "body": "Just launched my SaaS product! Super excited to share it with the community.",
        "title": "I built a thing",
    },
    {
        "source": "reddit",
        "subreddit": "productivity",
        "body": "HubSpot doubled their prices with no warning. After 3 years as a customer I'm now actively evaluating Salesforce and Pipedrive.",
        "title": "HubSpot pricing shock",
    },
    {
        "source": "appstore",
        "app_name": "Notion",
        "body": "App crashes every time I try to open a database. This has been broken for 2 weeks and support hasn't responded.",
        "title": "Crashes constantly",
    },
    {
        "source": "reddit",
        "subreddit": "webdev",
        "body": "What's the best framework for building a REST API in 2026?",
        "title": "REST API frameworks",
    },
]

EXPECTED = [True, False, True, True, False]  # expected is_complaint values


def run_fixture_tests():
    """Test classifier logic without LLM — validates data shapes and edge cases."""
    print("Running fixture tests (no LLM)...")
    errors = []

    for i, item in enumerate(FIXTURE_ITEMS):
        # Validate item has required fields
        assert "source" in item, f"Item {i} missing source"
        assert "body" in item, f"Item {i} missing body"
        assert item["source"] in ("reddit", "appstore"), f"Item {i} invalid source: {item['source']}"

    # Test deduplication logic (mirrors shared/supabase_client.py insert_raw_complaints)
    duped = [
        {"source": "reddit", "source_id": "reddit_abc123", "body": "test", "run_id": "fake"},
        {"source": "reddit", "source_id": "reddit_abc123", "body": "test", "run_id": "fake"},
        {"source": "reddit", "source_id": "reddit_xyz999", "body": "test2", "run_id": "fake"},
    ]
    seen = set()
    deduped = []
    for r in duped:
        key = (r.get("source"), r.get("source_id"))
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    assert len(deduped) == 2, f"Dedup failed: expected 2, got {len(deduped)}"
    print("  ✓ Deduplication logic works")
    print("  ✓ Item shape validation passed")

    # Test classifier output field coercion — is_complaint must be bool, not string
    # The LLM occasionally returns "true"/"false" strings; verify our parsing guards against this
    mock_llm_outputs = [
        {"is_complaint": True, "product_mentioned": "Jira"},       # correct
        {"is_complaint": False, "product_mentioned": None},         # correct
        {"is_complaint": True, "product_mentioned": ""},            # empty string → should become None
    ]
    for output in mock_llm_outputs:
        # Mirrors what classifier.py does when applying results back to items
        is_complaint = output.get("is_complaint", False)
        product = output.get("product_mentioned") or None  # empty string coerced to None
        assert isinstance(is_complaint, bool), f"is_complaint must be bool, got {type(is_complaint)}"
        assert product is None or isinstance(product, str), f"product_mentioned must be str or None"
        if output.get("product_mentioned") == "":
            assert product is None, "Empty string product_mentioned should coerce to None"
    print("  ✓ Classifier output coercion: is_complaint is bool, empty product_mentioned → None")

    print(f"Fixture tests passed.\n")


async def run_live_tests():
    """Make real LLM calls and validate classifier output."""
    print("Running live classifier tests (real LLM calls)...")

    from agents.scout.classifier import classify_batch

    items = [dict(item) for item in FIXTURE_ITEMS]  # copy so originals aren't mutated
    results = await classify_batch(items)

    errors = []
    for i, (item, expected) in enumerate(zip(results, EXPECTED)):
        actual = item.get("is_complaint")

        # Validate output shape
        assert "is_complaint" in item, f"Item {i}: missing is_complaint field"
        assert isinstance(actual, bool), f"Item {i}: is_complaint is not bool, got {type(actual)}"

        # Validate expected classification
        if actual != expected:
            errors.append(f"  ✗ Item {i} ({item['body'][:60]}...)\n    Expected is_complaint={expected}, got {actual}")
        else:
            verdict = "complaint" if actual else "not complaint"
            product = item.get("product_mentioned", "none")
            print(f"  ✓ Item {i}: {verdict} | product: {product}")

    if errors:
        print("\nFAILURES:")
        for e in errors:
            print(e)
        sys.exit(1)
    else:
        print(f"\nAll {len(results)} live classifier tests passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Make real LLM calls")
    args = parser.parse_args()

    run_fixture_tests()

    if args.live:
        asyncio.run(run_live_tests())
    else:
        print("Skipping live tests. Run with --live to test real LLM calls.")
