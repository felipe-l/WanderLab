"""Test Ranker's grouping, scoring, and bucketing logic.

Usage:
    cd tests
    python test_ranker_logic.py           # fixture tests only, no LLM calls
    python test_ranker_logic.py --live    # real LLM calls via OpenRouter
"""

import asyncio
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Fixture complaints — realistic data covering all bucket types
# ---------------------------------------------------------------------------

# Named product complaints — enough for strong clusters
NAMED_COMPLAINTS = [
    # Jira — 5 complaints (strong cluster)
    {"id": "uuid-001", "product_mentioned": "Jira", "body": "Jira pages take 15 seconds to load. We're a 30-person team and everyone hates it.", "is_complaint": True},
    {"id": "uuid-002", "product_mentioned": "JIRA", "body": "Atlassian Jira has gotten slower with every update. Evaluating Linear now.", "is_complaint": True},
    {"id": "uuid-003", "product_mentioned": "Atlassian Jira", "body": "Jira's mobile app crashes constantly. Support has been useless.", "is_complaint": True},
    {"id": "uuid-004", "product_mentioned": "jira", "body": "We pay $20/user/month for Jira and it's slower than free tools. About to cancel.", "is_complaint": True},
    {"id": "uuid-005", "product_mentioned": "Jira", "body": "Sprint planning in Jira requires 10 manual steps. A junior dev spent 2 hours just setting up a board.", "is_complaint": True},

    # HubSpot — 4 complaints (strong cluster)
    {"id": "uuid-006", "product_mentioned": "HubSpot", "body": "HubSpot doubled prices with zero notice. After 3 years I'm done.", "is_complaint": True},
    {"id": "uuid-007", "product_mentioned": "Hubspot", "body": "Hubspot CRM is way too complex for a 5-person team. I don't need enterprise features.", "is_complaint": True},
    {"id": "uuid-008", "product_mentioned": "HubSpot CRM", "body": "Moved from HubSpot to Pipedrive and halved our cost. HubSpot doesn't care about small businesses.", "is_complaint": True},
    {"id": "uuid-009", "product_mentioned": "hubspot", "body": "Their support is terrible. I've been waiting 3 weeks for a response on a billing issue.", "is_complaint": True},

    # Slack — 2 complaints (weak signal, below MIN_COMPLAINTS=3)
    {"id": "uuid-010", "product_mentioned": "Slack", "body": "Slack's search is so bad. Can't find anything older than a few months without paying.", "is_complaint": True},
    {"id": "uuid-011", "product_mentioned": "Slack", "body": "Notification overload. I've turned off everything but still get interrupted constantly.", "is_complaint": True},

    # Notion — 1 complaint (weak signal)
    {"id": "uuid-012", "product_mentioned": "Notion", "body": "Notion is too slow for a documentation tool. Pages take forever to load on mobile.", "is_complaint": True},
]

# Unmet need complaints — no product mentioned
UNMET_COMPLAINTS = [
    {"id": "uuid-101", "product_mentioned": None, "body": "There's no good tool for async meeting summaries that automatically sync to my calendar and project tracker.", "is_complaint": True},
    {"id": "uuid-102", "product_mentioned": None, "body": "I want something that writes my weekly status report for me based on what I actually did. Why doesn't this exist?", "is_complaint": True},
    {"id": "uuid-103", "product_mentioned": None, "body": "Spend 2 hours every Friday writing up what our team did. There has to be a better way.", "is_complaint": True},
    {"id": "uuid-104", "product_mentioned": None, "body": "I need a tool that automatically creates tickets from Slack conversations. Nothing does this well.", "is_complaint": True},
    {"id": "uuid-105", "product_mentioned": None, "body": "Why is there no product that detects when a customer is about to churn before they actually leave?", "is_complaint": True},
]

ALL_COMPLAINTS = NAMED_COMPLAINTS + UNMET_COMPLAINTS

MIN_COMPLAINTS = 3  # mirrors agents/ranker/main.py default


# ---------------------------------------------------------------------------
# Composite score calculation (mirrors themer.py)
# ---------------------------------------------------------------------------

def compute_composite(intensity: float, wtp: float, ai_rep: float) -> float:
    return round(0.35 * intensity + 0.35 * wtp + 0.30 * ai_rep, 3)


# ---------------------------------------------------------------------------
# Fixture tests
# ---------------------------------------------------------------------------

def test_named_vs_unmet_split():
    """Complaints split correctly into named product vs unmet needs buckets."""
    named = [c for c in ALL_COMPLAINTS if c.get("product_mentioned")]
    unmet = [c for c in ALL_COMPLAINTS if not c.get("product_mentioned")]

    assert len(named) == 12, f"Expected 12 named complaints, got {len(named)}"
    assert len(unmet) == 5, f"Expected 5 unmet complaints, got {len(unmet)}"
    assert len(named) + len(unmet) == len(ALL_COMPLAINTS)

    print(f"  ✓ Named/unmet split: {len(named)} named, {len(unmet)} unmet needs")
    return True


def test_product_grouping():
    """Products are grouped correctly by raw name before canonicalization."""
    from collections import defaultdict

    named = [c for c in ALL_COMPLAINTS if c.get("product_mentioned")]
    groups = defaultdict(list)
    for c in named:
        groups[c["product_mentioned"]].append(c)

    # Raw names (pre-canonicalization) — should have 8 distinct raw names
    assert "Jira" in groups
    assert "JIRA" in groups
    assert "jira" in groups
    assert "Atlassian Jira" in groups
    assert "HubSpot" in groups
    assert "Hubspot" in groups

    print(f"  ✓ Raw product grouping: {len(groups)} distinct raw product names before canonicalization")
    return True


def test_strong_vs_weak_bucketing():
    """Products with < MIN_COMPLAINTS go to weak signals, >= go to strong clusters."""
    from collections import defaultdict

    named = [c for c in ALL_COMPLAINTS if c.get("product_mentioned")]

    # Simulate canonical names (simplified — real canonicalization uses LLM)
    canonical_map = {
        "Jira": "Jira", "JIRA": "Jira", "jira": "Jira", "Atlassian Jira": "Jira",
        "HubSpot": "HubSpot", "Hubspot": "HubSpot", "HubSpot CRM": "HubSpot", "hubspot": "HubSpot",
        "Slack": "Slack",
        "Notion": "Notion",
    }
    for c in named:
        c["canonical_product"] = canonical_map.get(c["product_mentioned"], c["product_mentioned"])

    groups = defaultdict(list)
    for c in named:
        groups[c["canonical_product"]].append(c)

    strong = {p: cs for p, cs in groups.items() if len(cs) >= MIN_COMPLAINTS}
    weak = {p: cs for p, cs in groups.items() if len(cs) < MIN_COMPLAINTS}

    assert "Jira" in strong, "Jira (5 complaints) should be a strong cluster"
    assert "HubSpot" in strong, "HubSpot (4 complaints) should be a strong cluster"
    assert "Slack" in weak, "Slack (2 complaints) should be a weak signal"
    assert "Notion" in weak, "Notion (1 complaint) should be a weak signal"
    assert len(strong["Jira"]) == 5
    assert len(strong["HubSpot"]) == 4
    assert len(weak["Slack"]) == 2
    assert len(weak["Notion"]) == 1

    print(f"  ✓ Strong/weak bucketing: {len(strong)} strong clusters, {len(weak)} weak signals (MIN={MIN_COMPLAINTS})")
    return True


def test_weak_signal_cluster_shape():
    """Weak signal cluster records have correct shape and zero scores."""
    weak_product = "Slack"
    weak_complaints = [c for c in NAMED_COMPLAINTS if c.get("product_mentioned") == "Slack"]

    cluster = {
        "cluster_type": "weak_signal",
        "product_name": weak_product,
        "problem_theme": f"General complaints about {weak_product}",
        "complaint_count": len(weak_complaints),
        "raw_ids": [str(c["id"]) for c in weak_complaints if c.get("id")],
        "sample_complaints": [c.get("body", "")[:200] for c in weak_complaints[:3]],
        "intensity_score": 0.0,
        "wtp_score": 0.0,
        "ai_replaceability_score": 0.0,
        "composite_score": 0.0,
        "is_weak_signal": True,
    }

    assert cluster["cluster_type"] == "weak_signal"
    assert cluster["is_weak_signal"] is True
    assert cluster["composite_score"] == 0.0
    assert cluster["complaint_count"] == 2
    assert len(cluster["raw_ids"]) == 2
    assert len(cluster["sample_complaints"]) == 2
    print("  ✓ Weak signal cluster shape: correct structure and zero scores")
    return True


def test_composite_score_formula():
    """Composite score = 0.35×intensity + 0.35×wtp + 0.30×ai_rep."""
    cases = [
        # (intensity, wtp, ai_rep, expected)
        (0.9, 0.8, 0.9, round(0.35 * 0.9 + 0.35 * 0.8 + 0.30 * 0.9, 3)),
        (0.5, 0.5, 0.5, 0.5),
        (1.0, 1.0, 1.0, 1.0),
        (0.0, 0.0, 0.0, 0.0),
        (0.6, 0.3, 0.9, round(0.35 * 0.6 + 0.35 * 0.3 + 0.30 * 0.9, 3)),
    ]

    for intensity, wtp, ai_rep, expected in cases:
        result = compute_composite(intensity, wtp, ai_rep)
        assert abs(result - expected) < 0.001, (
            f"Composite({intensity}, {wtp}, {ai_rep}) = {result}, expected {expected}"
        )

    print(f"  ✓ Composite score formula: 0.35×intensity + 0.35×wtp + 0.30×ai_rep verified ({len(cases)} cases)")
    return True


def test_composite_score_clamped():
    """Scores out of [0, 1] range are clamped before composite calculation."""
    # Mirrors themer.py: max(0.0, min(1.0, value))
    intensity = max(0.0, min(1.0, 1.5))   # should clamp to 1.0
    wtp = max(0.0, min(1.0, -0.2))         # should clamp to 0.0
    ai_rep = max(0.0, min(1.0, 0.7))

    assert intensity == 1.0
    assert wtp == 0.0
    assert ai_rep == 0.7

    composite = compute_composite(intensity, wtp, ai_rep)
    assert 0.0 <= composite <= 1.0, f"Composite score {composite} is out of range"
    print("  ✓ Score clamping: out-of-range values are clamped to [0.0, 1.0]")
    return True


def test_clusters_sorted_by_composite():
    """Strong clusters sorted descending by composite_score — Analyst reads top N."""
    clusters = [
        {"product_name": "Jira", "composite_score": 0.72, "is_weak_signal": False},
        {"product_name": "HubSpot", "composite_score": 0.81, "is_weak_signal": False},
        {"product_name": "Notion", "composite_score": 0.55, "is_weak_signal": False},
        {"product_name": "Figma", "composite_score": 0.91, "is_weak_signal": False},
        {"product_name": "Slack", "composite_score": 0.0, "is_weak_signal": True},
    ]

    strong = [c for c in clusters if not c.get("is_weak_signal")]
    strong.sort(key=lambda x: x["composite_score"], reverse=True)

    assert strong[0]["product_name"] == "Figma"
    assert strong[1]["product_name"] == "HubSpot"
    assert strong[2]["product_name"] == "Jira"
    assert strong[3]["product_name"] == "Notion"
    assert len(strong) == 4  # weak signals excluded

    print("  ✓ Cluster sorting: strong clusters ordered by composite_score descending, weak signals excluded")
    return True


def test_unmet_need_composite_score():
    """Unmet need composite = ai_replaceability * 0.5 (no intensity/WTP signal)."""
    ai_rep = 0.8
    expected = round(ai_rep * 0.5, 3)

    # Mirrors synthesize_unmet_needs in themer.py
    cluster = {
        "cluster_type": "unmet_need",
        "intensity_score": 0.0,
        "wtp_score": 0.0,
        "ai_replaceability_score": ai_rep,
        "composite_score": round(ai_rep * 0.5, 3),
    }

    assert cluster["composite_score"] == expected
    assert cluster["intensity_score"] == 0.0
    assert cluster["wtp_score"] == 0.0
    print(f"  ✓ Unmet need scoring: composite = ai_rep × 0.5 = {expected} (no intensity/WTP for unmet needs)")
    return True


def test_raw_ids_mapped_from_indices():
    """raw_ids must map back from LLM's raw_indices to actual complaint UUIDs."""
    complaints = [
        {"id": "uuid-001", "body": "complaint A"},
        {"id": "uuid-002", "body": "complaint B"},
        {"id": "uuid-003", "body": "complaint C"},
        {"id": "uuid-004", "body": "complaint D"},
    ]

    # Simulate LLM returning raw_indices [0, 2] for a theme
    raw_indices = [0, 2]
    raw_ids = [
        str(complaints[i]["id"])
        for i in raw_indices
        if i < len(complaints) and complaints[i].get("id")
    ]

    assert raw_ids == ["uuid-001", "uuid-003"]
    print("  ✓ raw_ids mapping: LLM raw_indices correctly mapped to complaint UUIDs")
    return True


def test_out_of_bounds_raw_indices_ignored():
    """Out-of-bounds raw_indices from LLM are silently ignored (no crash)."""
    complaints = [
        {"id": "uuid-001", "body": "complaint A"},
        {"id": "uuid-002", "body": "complaint B"},
    ]

    # LLM sometimes hallucinates indices beyond the list length
    raw_indices = [0, 5, 99, 1]  # 5 and 99 are out of bounds
    raw_ids = [
        str(complaints[i]["id"])
        for i in raw_indices
        if i < len(complaints) and complaints[i].get("id")
    ]

    assert raw_ids == ["uuid-001", "uuid-002"]
    print("  ✓ Out-of-bounds indices: silently ignored, no IndexError")
    return True


def test_cluster_type_values():
    """cluster_type must be one of the 3 values allowed by the DB constraint."""
    valid_types = {"product", "unmet_need", "weak_signal"}

    test_clusters = [
        {"cluster_type": "product"},
        {"cluster_type": "unmet_need"},
        {"cluster_type": "weak_signal"},
    ]

    for cluster in test_clusters:
        assert cluster["cluster_type"] in valid_types, (
            f"Invalid cluster_type '{cluster['cluster_type']}' — DB constraint will reject"
        )

    print(f"  ✓ cluster_type values: all valid for DB constraint {valid_types}")
    return True


# ---------------------------------------------------------------------------
# Live tests
# ---------------------------------------------------------------------------

async def run_live_themer():
    """Real LLM call — theme identification for a product cluster."""
    print("\nLive themer test (Sonnet call)...")
    from agents.ranker.themer import identify_themes

    complaints = [
        {"id": f"uuid-{i:03d}", "body": body}
        for i, body in enumerate([
            "Jira pages take 15+ seconds to load. Every ticket update is painful. We're evaluating Linear.",
            "We pay $20/user/month for Jira and it's slower than free alternatives. Performance is unacceptable.",
            "Sprint planning in Jira takes 2 hours because of slow load times and confusing UI. Looking at alternatives.",
            "Jira's mobile app is completely broken. Crashes on startup. Atlassian support hasn't responded in 2 weeks.",
            "Just cancelled our Jira subscription after 4 years. The performance has gotten worse, not better.",
        ])
    ]

    themes = await identify_themes("Jira", complaints)

    assert len(themes) > 0, "Expected at least 1 theme from Jira complaints"

    for theme in themes:
        assert "cluster_type" in theme and theme["cluster_type"] == "product"
        assert "product_name" in theme and theme["product_name"] == "Jira"
        assert "problem_theme" in theme and theme["problem_theme"]
        assert "composite_score" in theme
        assert 0.0 <= theme["composite_score"] <= 1.0
        assert "sample_complaints" in theme and len(theme["sample_complaints"]) > 0
        assert "is_weak_signal" in theme and theme["is_weak_signal"] is False

        # Verify formula
        expected = compute_composite(
            theme["intensity_score"],
            theme["wtp_score"],
            theme["ai_replaceability_score"],
        )
        assert abs(theme["composite_score"] - expected) < 0.01, (
            f"Composite score mismatch: got {theme['composite_score']}, expected {expected}"
        )

    print(f"  ✓ Live themer: {len(themes)} themes identified for Jira")
    for t in themes:
        print(f"    - '{t['problem_theme']}' (composite: {t['composite_score']:.2f})")
    return True


async def run_live_unmet_needs():
    """Real LLM call — unmet needs synthesis."""
    print("\nLive unmet needs test (Sonnet call)...")
    from agents.ranker.themer import synthesize_unmet_needs

    complaints = [
        {"id": f"uuid-{i:03d}", "body": body}
        for i, body in enumerate([
            "There's no good tool for writing my weekly status report based on actual git commits and Slack messages.",
            "I want to auto-generate standup notes from what I actually did in Jira and GitHub. Why doesn't this exist?",
            "Spend 3 hours a week writing the same status updates. Would pay good money for AI that does this for me.",
            "No tool automatically summarizes async meetings and pushes action items to my todo list.",
            "I've been asking for auto-meeting-notes that sync to Linear tickets for years. Still nothing good.",
            "Why can't my CRM automatically detect when a customer is about to churn before they ghost me?",
            "Churn prediction tools exist but they're all for enterprise with $50k/yr price tags. Nothing for SMBs.",
        ])
    ]

    themes = await synthesize_unmet_needs(complaints, top_n=3)

    assert len(themes) > 0, "Expected at least 1 unmet need theme"

    for theme in themes:
        assert "cluster_type" in theme and theme["cluster_type"] == "unmet_need"
        assert "product_name" in theme and theme["product_name"] is None
        assert "problem_theme" in theme and theme["problem_theme"]
        assert "composite_score" in theme
        assert 0.0 <= theme["composite_score"] <= 0.5, (
            f"Unmet need composite should be ≤ 0.5 (ai_rep × 0.5), got {theme['composite_score']}"
        )

    print(f"  ✓ Live unmet needs: {len(themes)} themes identified")
    for t in themes:
        print(f"    - '{t['problem_theme']}' (composite: {t['composite_score']:.2f})")
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Make real LLM calls")
    args = parser.parse_args()

    print("Running Ranker logic tests...\n")

    fixture_results = [
        test_named_vs_unmet_split(),
        test_product_grouping(),
        test_strong_vs_weak_bucketing(),
        test_weak_signal_cluster_shape(),
        test_composite_score_formula(),
        test_composite_score_clamped(),
        test_clusters_sorted_by_composite(),
        test_unmet_need_composite_score(),
        test_raw_ids_mapped_from_indices(),
        test_out_of_bounds_raw_indices_ignored(),
        test_cluster_type_values(),
    ]

    passed = sum(fixture_results)
    total = len(fixture_results)
    print(f"\n{passed}/{total} fixture tests passed.")

    if args.live:
        print("\nRunning live tests (real LLM calls)...")
        async def run_live():
            return await asyncio.gather(
                run_live_themer(),
                run_live_unmet_needs(),
            )
        live_results = asyncio.run(run_live())
        live_passed = sum(live_results)
        print(f"\n{live_passed}/{len(live_results)} live tests passed.")
        if live_passed < len(live_results):
            sys.exit(1)

    if passed < total:
        sys.exit(1)
    else:
        if not args.live:
            print("\nRun with --live to test real LLM calls (Sonnet).")
