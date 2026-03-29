"""Test Ranker's product name canonicalization.

Usage:
    cd tests
    python test_ranker_canonicalizer.py           # fixture only
    python test_ranker_canonicalizer.py --live    # real LLM calls
"""

import asyncio
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


FIXTURE_VARIANTS = [
    "JIRA", "Jira", "Atlassian Jira", "jira",
    "HubSpot", "Hubspot", "hubspot", "HubSpot CRM",
    "MS Teams", "Microsoft Teams", "Teams",
    "Notion", "notion",
    "Slack",
]

# After canonicalization, these groups should map to the same name
EXPECTED_GROUPS = {
    "Jira": ["JIRA", "Jira", "Atlassian Jira", "jira"],
    "HubSpot": ["HubSpot", "Hubspot", "hubspot", "HubSpot CRM"],
    "Microsoft Teams": ["MS Teams", "Microsoft Teams", "Teams"],
}


async def run_live_tests():
    print("Running live canonicalization tests...")

    from agents.ranker.canonicalizer import canonicalize_product_names

    mapping = await canonicalize_product_names(FIXTURE_VARIANTS)

    print(f"  Raw mapping: {mapping}\n")

    errors = []
    for canonical, variants in EXPECTED_GROUPS.items():
        canonical_values = set(mapping.get(v) for v in variants if v in mapping)
        if len(canonical_values) != 1:
            errors.append(f"  ✗ {canonical}: variants mapped to multiple names: {canonical_values}")
        else:
            actual = list(canonical_values)[0]
            print(f"  ✓ {canonical}: all variants → '{actual}'")

    if errors:
        print("\nFAILURES:")
        for e in errors:
            print(e)
        sys.exit(1)
    else:
        print(f"\nAll canonicalization tests passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    if args.live:
        asyncio.run(run_live_tests())
    else:
        print("No fixture tests for canonicalization — run with --live to test real LLM calls.")
