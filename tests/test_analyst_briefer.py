"""Test Analyst's brief generation — output shape, required fields, and verdict values.

Usage:
    cd tests
    python test_analyst_briefer.py           # fixture tests only, no LLM calls
    python test_analyst_briefer.py --live    # real LLM calls via OpenRouter (Sonnet)
"""

import asyncio
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Required fields per brief type
# ---------------------------------------------------------------------------

PRODUCT_BRIEF_REQUIRED_FIELDS = [
    "product_concept",
    "core_problem",
    "buyer_profile",
    "what_incumbent_gets_wrong",
    "wedge",
    "build_complexity",
    "verdict",
    "verdict_rationale",
]

UNMET_NEED_BRIEF_REQUIRED_FIELDS = [
    "product_concept",
    "core_problem",
    "buyer_profile",
    "why_no_solution_exists",
    "wedge",
    "build_complexity",
    "verdict",
    "verdict_rationale",
]

VALID_VERDICTS = {"build", "watch", "skip"}
VALID_COMPLEXITIES = {"weekend", "1 month", "3+ months"}

# Fields that briefer.py always injects (not from LLM)
INJECTED_FIELDS = ["ranked_id", "product_name", "problem_theme", "evidence_count", "avg_composite_score", "cluster_type"]


# ---------------------------------------------------------------------------
# Fixture cluster data
# ---------------------------------------------------------------------------

PRODUCT_CLUSTER_JIRA = {
    "id": "ranked-uuid-001",
    "cluster_type": "product",
    "product_name": "Jira",
    "problem_theme": "Performance and slow load times",
    "complaint_count": 18,
    "composite_score": 0.78,
    "intensity_score": 0.85,
    "wtp_score": 0.80,
    "ai_replaceability_score": 0.70,
    "sample_complaints": [
        "Jira pages take 15+ seconds to load. Every ticket update is a waiting game. We're evaluating Linear seriously.",
        "We pay $20/user/month for this? Our team spends more time waiting for Jira than doing actual work.",
        "Sprint planning meetings run 2 hours just because of Jira's sluggish UI. We've had enough.",
        "Just switched to Linear after 4 years on Jira. Performance difference is insane. Zero regrets.",
        "Jira's search is broken — can never find anything and when I do, clicking it takes forever.",
    ],
}

PRODUCT_CLUSTER_HUBSPOT = {
    "id": "ranked-uuid-002",
    "cluster_type": "product",
    "product_name": "HubSpot",
    "problem_theme": "Pricing shock and value mismatch for SMBs",
    "complaint_count": 12,
    "composite_score": 0.81,
    "intensity_score": 0.90,
    "wtp_score": 0.85,
    "ai_replaceability_score": 0.65,
    "sample_complaints": [
        "HubSpot doubled our bill with 2 weeks notice. After 3 years as a loyal customer I'm actively shopping alternatives.",
        "We're a 6-person startup — we don't need enterprise CRM features. HubSpot bundles everything and charges for all of it.",
        "Moved to Pipedrive and saved $800/month. HubSpot has completely forgotten small businesses exist.",
    ],
}

PRODUCT_CLUSTER_FIGMA = {
    "id": "ranked-uuid-003",
    "cluster_type": "product",
    "product_name": "Figma",
    "problem_theme": "Dev handoff is manual and error-prone",
    "complaint_count": 8,
    "composite_score": 0.69,
    "intensity_score": 0.65,
    "wtp_score": 0.60,
    "ai_replaceability_score": 0.85,
    "sample_complaints": [
        "Our devs constantly misinterpret Figma specs. We have to re-explain the same designs in Slack every sprint.",
        "Dev handoff from Figma is still basically 'send a link and hope for the best'. It's 2026.",
        "Figma's inspect panel shows measurements but doesn't tell devs WHY design decisions were made.",
    ],
}

UNMET_NEED_CLUSTER = {
    "id": "ranked-uuid-004",
    "cluster_type": "unmet_need",
    "product_name": None,
    "problem_theme": "Auto-generated status reports from engineering activity",
    "complaint_count": 14,
    "composite_score": 0.40,
    "intensity_score": 0.0,
    "wtp_score": 0.0,
    "ai_replaceability_score": 0.80,
    "sample_complaints": [
        "I spend 3 hours every Friday writing the same status update from git logs and Jira tickets. This should be automated.",
        "Why is there no tool that reads my GitHub commits and Jira activity and writes my standup for me?",
        "Our leadership wants weekly engineering reports. I spend Monday mornings writing instead of building.",
        "I'd pay $50/month for something that auto-generates my status report from actual work done.",
    ],
}

PRODUCT_CLUSTER_MISSING_FIELDS = {
    "id": "ranked-uuid-005",
    "cluster_type": "product",
    "product_name": "Notion",
    "problem_theme": "Mobile performance",
    "complaint_count": 3,
    "composite_score": 0.50,
    "intensity_score": 0.50,
    "wtp_score": 0.50,
    "ai_replaceability_score": 0.50,
    "sample_complaints": [],  # empty — tests graceful handling
}


# ---------------------------------------------------------------------------
# Fixture: simulate a valid LLM response for a product brief
# ---------------------------------------------------------------------------

MOCK_PRODUCT_BRIEF_RESPONSE = {
    "product_concept": "An AI-native project tracker that auto-generates sprint reports, predicts bottlenecks, and syncs updates in real-time — built for 5-50 person startups who find Jira too slow.",
    "core_problem": "Jira's performance is so bad that teams spend more time waiting for the tool than using it, eroding trust and wasting hours every sprint.",
    "buyer_profile": "Engineering managers and CTOs at 10-100 person startups, currently paying $8-20/user/month for Jira and actively evaluating alternatives.",
    "what_incumbent_gets_wrong": "Jira was architected for large enterprises with slow round-trips to centralized servers. Speed was never a design priority because enterprise buyers don't feel the pain directly.",
    "wedge": "Free Jira CSV importer + a landing page targeting 'Jira alternatives' searches. First users from r/projectmanagement and Linear community Discord.",
    "build_complexity": "1 month",
    "build_complexity_rationale": "Core tracker is table stakes; the differentiation is the AI sprint summarization layer, which is 2-3 weeks of work.",
    "verdict": "build",
    "verdict_rationale": "18 complaints with high intensity and WTP signal. Users are already switching — they just need a better option. The AI angle on sprint planning and status updates is a real differentiator.",
}

MOCK_UNMET_NEED_RESPONSE = {
    "product_concept": "An AI agent that reads your GitHub commits, Jira tickets, and Slack messages to auto-draft your weekly engineering status report — reviewed and sent in under 60 seconds.",
    "core_problem": "Engineering teams spend hours every week manually writing status reports that could be generated from work already logged in their tools.",
    "buyer_profile": "Individual contributors and engineering leads at companies with 10-200 engineers where leadership requires weekly written updates.",
    "why_no_solution_exists": "Requires tight integration with 3+ enterprise tools (GitHub, Jira, Slack) and enough AI quality to produce readable prose — technically possible now but no one has nailed the UX.",
    "wedge": "Free Chrome extension that scrapes your GitHub activity page and generates a sample report — zero integration required to see value on day 1.",
    "build_complexity": "1 month",
    "build_complexity_rationale": "Integrations are the hard part; the LLM summarization is straightforward once you have the data.",
    "verdict": "build",
    "verdict_rationale": "Clear recurring pain, explicit WTP signals ('I'd pay $50/month'), and AI is the obvious solution. The challenge is distribution — this needs to be found by people who are currently writing reports manually.",
}


# ---------------------------------------------------------------------------
# Fixture tests — no LLM calls
# ---------------------------------------------------------------------------

def test_product_brief_required_fields():
    """A valid LLM response contains all required product brief fields."""
    errors = []
    for field in PRODUCT_BRIEF_REQUIRED_FIELDS:
        if field not in MOCK_PRODUCT_BRIEF_RESPONSE:
            errors.append(f"  ✗ Missing required field: {field}")
        elif not MOCK_PRODUCT_BRIEF_RESPONSE[field]:
            errors.append(f"  ✗ Field is empty: {field}")

    if errors:
        for e in errors:
            print(e)
        return False

    print(f"  ✓ Product brief required fields: all {len(PRODUCT_BRIEF_REQUIRED_FIELDS)} fields present and non-empty")
    return True


def test_unmet_need_brief_required_fields():
    """Unmet need brief has its own required fields (why_no_solution_exists instead of what_incumbent_gets_wrong)."""
    errors = []
    for field in UNMET_NEED_BRIEF_REQUIRED_FIELDS:
        if field not in MOCK_UNMET_NEED_RESPONSE:
            errors.append(f"  ✗ Missing required field: {field}")
        elif not MOCK_UNMET_NEED_RESPONSE[field]:
            errors.append(f"  ✗ Field is empty: {field}")

    assert "why_no_solution_exists" in MOCK_UNMET_NEED_RESPONSE, \
        "Unmet need brief should have why_no_solution_exists, not what_incumbent_gets_wrong"
    assert "what_incumbent_gets_wrong" not in MOCK_UNMET_NEED_RESPONSE, \
        "Unmet need brief should not have what_incumbent_gets_wrong"

    if errors:
        for e in errors:
            print(e)
        return False

    print(f"  ✓ Unmet need brief required fields: all {len(UNMET_NEED_BRIEF_REQUIRED_FIELDS)} fields present")
    return True


def test_verdict_values():
    """Verdict must be one of: build, watch, skip."""
    assert MOCK_PRODUCT_BRIEF_RESPONSE["verdict"] in VALID_VERDICTS
    assert MOCK_UNMET_NEED_RESPONSE["verdict"] in VALID_VERDICTS

    invalid = {"BUILD", "Watch", "SKIP", "maybe", "yes", "no", ""}
    for v in invalid:
        assert v not in VALID_VERDICTS, f"'{v}' should not be a valid verdict"

    print(f"  ✓ Verdict validation: only {VALID_VERDICTS} are valid")
    return True


def test_build_complexity_values():
    """build_complexity must be one of: weekend, 1 month, 3+ months."""
    assert MOCK_PRODUCT_BRIEF_RESPONSE["build_complexity"] in VALID_COMPLEXITIES
    assert MOCK_UNMET_NEED_RESPONSE["build_complexity"] in VALID_COMPLEXITIES

    invalid = {"1 week", "2 months", "fast", "hard", ""}
    for v in invalid:
        assert v not in VALID_COMPLEXITIES, f"'{v}' should not be a valid build_complexity"

    print(f"  ✓ Build complexity validation: only {VALID_COMPLEXITIES} are valid")
    return True


def test_briefer_injects_metadata_fields():
    """briefer.py always injects ranked_id, product_name, problem_theme, etc. from the cluster."""
    # Simulate what briefer.generate_product_brief does after getting LLM response
    cluster = PRODUCT_CLUSTER_JIRA
    result = dict(MOCK_PRODUCT_BRIEF_RESPONSE)

    result["ranked_id"] = str(cluster.get("id", ""))
    result["product_name"] = cluster.get("product_name")
    result["problem_theme"] = cluster.get("problem_theme")
    result["evidence_count"] = cluster.get("complaint_count", 0)
    result["avg_composite_score"] = cluster.get("composite_score", 0)
    result["cluster_type"] = "product"

    for field in INJECTED_FIELDS:
        assert field in result, f"Injected field '{field}' missing"
        assert result[field] is not None or field == "product_name", f"Injected field '{field}' is None"

    assert result["ranked_id"] == "ranked-uuid-001"
    assert result["product_name"] == "Jira"
    assert result["evidence_count"] == 18
    assert result["avg_composite_score"] == 0.78

    print("  ✓ Briefer metadata injection: ranked_id, product_name, evidence_count, etc. correctly attached")
    return True


def test_unmet_need_product_name_is_none():
    """Unmet need briefs always have product_name=None — they represent market gaps."""
    result = dict(MOCK_UNMET_NEED_RESPONSE)
    result["ranked_id"] = str(UNMET_NEED_CLUSTER.get("id", ""))
    result["product_name"] = None  # explicitly None for unmet needs
    result["problem_theme"] = UNMET_NEED_CLUSTER.get("problem_theme")
    result["cluster_type"] = "unmet_need"

    assert result["product_name"] is None, "Unmet need brief must have product_name=None"
    assert result["cluster_type"] == "unmet_need"
    print("  ✓ Unmet need product_name: correctly set to None")
    return True


def test_supabase_record_shape():
    """Records written to pipeline_opportunities have all required columns."""
    brief = dict(MOCK_PRODUCT_BRIEF_RESPONSE)
    brief.update({
        "ranked_id": "ranked-uuid-001",
        "product_name": "Jira",
        "problem_theme": "Performance and slow load times",
        "evidence_count": 18,
        "avg_composite_score": 0.78,
        "cluster_type": "product",
    })

    # Mirrors what analyst/main.py builds before insert_opportunities
    record = {
        "ranked_id": brief.get("ranked_id"),
        "product_name": brief.get("product_name") or "Market Gap",
        "problem_summary": brief.get("core_problem", ""),
        "evidence_count": brief.get("evidence_count", 0),
        "avg_composite_score": brief.get("avg_composite_score", 0),
        "opportunity_brief": brief.get("product_concept", ""),
        "verdict": brief.get("verdict", "skip"),
        "verdict_rationale": brief.get("verdict_rationale", ""),
        "filtered_ids": [],
        "buyer_profile": brief.get("buyer_profile"),
        "wedge": brief.get("wedge"),
        "build_complexity": brief.get("build_complexity"),
        "product_concept": brief.get("product_concept"),
    }

    required_columns = [
        "ranked_id", "product_name", "problem_summary", "evidence_count",
        "avg_composite_score", "opportunity_brief", "verdict", "verdict_rationale",
        "filtered_ids", "buyer_profile", "wedge", "build_complexity", "product_concept",
    ]

    for col in required_columns:
        assert col in record, f"Missing Supabase column: {col}"

    assert record["verdict"] in VALID_VERDICTS
    assert isinstance(record["filtered_ids"], list)
    assert record["product_name"] == "Jira"

    print(f"  ✓ Supabase record shape: all {len(required_columns)} columns present and valid")
    return True


def test_none_brief_filtered_out():
    """Briefs that fail LLM generation (return None) are filtered before Supabase insert."""
    briefs = [
        MOCK_PRODUCT_BRIEF_RESPONSE,
        None,  # simulate failed LLM call
        MOCK_UNMET_NEED_RESPONSE,
        None,  # another failure
    ]

    valid_briefs = [b for b in briefs if b is not None]

    assert len(valid_briefs) == 2
    assert all(b is not None for b in valid_briefs)
    print("  ✓ Failed brief filtering: None results excluded before Supabase insert")
    return True


def test_sample_complaints_attached_from_cluster():
    """After brief generation, sample_complaints from the ranked cluster are attached for Discord formatting."""
    cluster = PRODUCT_CLUSTER_JIRA
    brief = dict(MOCK_PRODUCT_BRIEF_RESPONSE)
    brief["ranked_id"] = str(cluster.get("id", ""))
    brief["product_name"] = cluster.get("product_name")

    # Simulate how analyst/main.py attaches sample_complaints
    cluster_map = {str(cluster["id"]): cluster}
    matched_cluster = cluster_map.get(brief["ranked_id"], {})
    brief["sample_complaints"] = matched_cluster.get("sample_complaints", [])

    assert brief["sample_complaints"] == cluster["sample_complaints"]
    assert len(brief["sample_complaints"]) == 5
    print("  ✓ Sample complaints attachment: cluster quotes correctly attached to brief for Discord formatting")
    return True


# ---------------------------------------------------------------------------
# Live tests
# ---------------------------------------------------------------------------

async def run_live_product_brief():
    """Real Sonnet call — generate a brief for a strong product cluster."""
    print("\nLive product brief test (Sonnet call)...")
    from agents.analyst.briefer import generate_product_brief

    brief = await generate_product_brief(PRODUCT_CLUSTER_JIRA)

    assert brief is not None, "Expected a brief, got None — LLM call failed"

    errors = []
    for field in PRODUCT_BRIEF_REQUIRED_FIELDS:
        if field not in brief:
            errors.append(f"  ✗ Missing required field: {field}")
        elif not brief[field]:
            errors.append(f"  ✗ Field is empty: {field}")

    if errors:
        for e in errors:
            print(e)
        return False

    assert brief.get("verdict") in VALID_VERDICTS, \
        f"Invalid verdict: '{brief.get('verdict')}' — must be one of {VALID_VERDICTS}"
    assert brief.get("build_complexity") in VALID_COMPLEXITIES, \
        f"Invalid build_complexity: '{brief.get('build_complexity')}' — must be one of {VALID_COMPLEXITIES}"

    # Verify injected metadata
    assert brief.get("product_name") == "Jira"
    assert brief.get("cluster_type") == "product"
    assert brief.get("evidence_count") == 18

    print(f"  ✓ Live product brief (Jira): verdict={brief['verdict']}, complexity={brief['build_complexity']}")
    print(f"    Concept: {brief['product_concept'][:80]}...")
    return True


async def run_live_hubspot_brief():
    """Real Sonnet call — test a pricing/value complaint cluster."""
    print("\nLive HubSpot brief test (Sonnet call)...")
    from agents.analyst.briefer import generate_product_brief

    brief = await generate_product_brief(PRODUCT_CLUSTER_HUBSPOT)

    assert brief is not None, "Expected a brief, got None"
    assert brief.get("verdict") in VALID_VERDICTS
    assert brief.get("product_name") == "HubSpot"

    print(f"  ✓ Live product brief (HubSpot pricing): verdict={brief['verdict']}, complexity={brief['build_complexity']}")
    print(f"    Wedge: {brief.get('wedge', '')[:80]}...")
    return True


async def run_live_unmet_need_brief():
    """Real Sonnet call — generate a brief for an unmet need cluster."""
    print("\nLive unmet need brief test (Sonnet call)...")
    from agents.analyst.briefer import generate_unmet_need_brief

    brief = await generate_unmet_need_brief(UNMET_NEED_CLUSTER)

    assert brief is not None, "Expected a brief, got None"

    errors = []
    for field in UNMET_NEED_BRIEF_REQUIRED_FIELDS:
        if field not in brief:
            errors.append(f"  ✗ Missing required field: {field}")
        elif not brief[field]:
            errors.append(f"  ✗ Field is empty: {field}")

    if errors:
        for e in errors:
            print(e)
        return False

    assert "what_incumbent_gets_wrong" not in brief, \
        "Unmet need brief should not have 'what_incumbent_gets_wrong'"
    assert brief.get("product_name") is None
    assert brief.get("cluster_type") == "unmet_need"
    assert brief.get("verdict") in VALID_VERDICTS

    print(f"  ✓ Live unmet need brief: verdict={brief['verdict']}, complexity={brief['build_complexity']}")
    print(f"    Theme: {UNMET_NEED_CLUSTER['problem_theme']}")
    return True


async def run_live_high_ai_cluster():
    """Sonnet call on a cluster with high AI replaceability — should lean toward 'build'."""
    print("\nLive high-AI-replaceability brief test (Figma devhandoff, Sonnet call)...")
    from agents.analyst.briefer import generate_product_brief

    brief = await generate_product_brief(PRODUCT_CLUSTER_FIGMA)

    assert brief is not None, "Expected a brief, got None"
    assert brief.get("verdict") in VALID_VERDICTS

    # With ai_replaceability=0.85, we expect the LLM to lean toward build or watch
    print(f"  ✓ Live high-AI brief (Figma dev handoff): verdict={brief['verdict']}")
    print(f"    AI angle: {brief.get('product_concept', '')[:80]}...")
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Make real LLM calls (Sonnet)")
    args = parser.parse_args()

    print("Running Analyst briefer tests...\n")

    fixture_results = [
        test_product_brief_required_fields(),
        test_unmet_need_brief_required_fields(),
        test_verdict_values(),
        test_build_complexity_values(),
        test_briefer_injects_metadata_fields(),
        test_unmet_need_product_name_is_none(),
        test_supabase_record_shape(),
        test_none_brief_filtered_out(),
        test_sample_complaints_attached_from_cluster(),
    ]

    passed = sum(fixture_results)
    total = len(fixture_results)
    print(f"\n{passed}/{total} fixture tests passed.")

    if args.live:
        print("\nRunning live tests (real Sonnet calls — ~$0.05-0.10)...")
        async def run_live():
            return await asyncio.gather(
                run_live_product_brief(),
                run_live_hubspot_brief(),
                run_live_unmet_need_brief(),
                run_live_high_ai_cluster(),
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
            print("\nRun with --live to test real Sonnet calls (4 briefs, ~$0.05-0.10).")
