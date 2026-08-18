#!/usr/bin/env python3
"""scan_jobs.py — Scan agentic AI job boards for high-alignment remote roles.

Fetches from agentic-engineering-jobs.com API, filters for remote + senior/staff +
agentic AI, scores on profile alignment (loaded from profile.json), and surfaces top
matches with heuristic keyword signals (not assessments) for viability, product substance, and moat.

Usage:
    python3 scan_jobs.py [--profile profile.json] [--pages N] [--top N] [--min-score N]

    --profile    Path to profile config (default: profile.json or profile.example.json)
    --pages N    API pages to fetch (default: 5, ~250 jobs)
    --top N      Results to return (default: 3)
    --min-score  Minimum alignment score (default: 8)
"""
import json
import sys
import os
import urllib.request
import urllib.parse
import re
import argparse
from datetime import datetime, timezone

API_BASE = "https://agentic-engineering-jobs.com/api/v1/jobs"

# Viability signals — evidence the company is default-alive or profitable
VIABILITY_POSITIVE = [
    "profitable", "default alive", "revenue", "arr", "mrr", "paying customers",
    "break-even", "positive cash flow", "self-sustaining", "series c", "series d",
    "series e", "series f", "ipo", "publicly traded", "nasdaq", "nyse",
    "acquisition", "acquired", "merger", "fortune 500", "fortune 100",
    "enterprise customers", "paying enterprise", "contract revenue",
    "government contract", "dod", "doe", "federal",
]
VIABILITY_NEGATIVE = [
    "pre-revenue", "pre-seed", "seed round", "burn rate", "runway",
    "raise capital", "seeking funding", "fundraising",
]

# Agentic substance signals — evidence they've built something real, not hype
PRODUCT_SUBSTANCE_POSITIVE = [
    "production", "shipped", "deployed", "operational", "in production",
    "real users", "real customers", "live", "serving", "powering",
    "mission-critical", "production-grade", "production-ready",
    "millions of", "billions of", "enterprise-scale", "at scale",
    "operational history", "real failure modes", "incident",
    "customer-facing", "customer-ready", "real-world",
]
PRODUCT_SUBSTANCE_NEGATIVE = [
    "prototype", "proof of concept", "poc", "demo", "exploring",
    "experimenting", "research", "pilot", "early stage",
    "we're building", "we plan to", "we envision", "we aspire",
    "eventually", "in the future", "roadmap",
]


def load_profile(path):
    """Load the user's profile configuration."""
    with open(path) as f:
        return json.load(f)


def build_keyword_scores(profile):
    """Build the keyword->points map from the profile's tech stack + scoring weights."""
    weights = profile.get("scoring_weights", {})
    tech = profile.get("tech_stack", {})
    kw = {}

    # Primary languages get the primary_language weight
    primary_weight = weights.get("primary_language", 3)
    for lang in tech.get("primary", []):
        kw[lang] = primary_weight

    # Secondary languages get a lower weight
    for lang in tech.get("secondary", []):
        kw[lang] = 1

    # AI infra keywords get the mcp weight if they're MCP-adjacent, else agent_orchestration
    mcp_weight = weights.get("mcp", 3)
    orch_weight = weights.get("agent_orchestration", 2)
    eval_weight = weights.get("eval_observability", 2)
    cloud_weight = weights.get("cloud_infra", 2)

    for ai_kw in tech.get("ai", []):
        if "mcp" in ai_kw or "model context protocol" in ai_kw:
            kw[ai_kw] = mcp_weight
        elif "orchestrat" in ai_kw or "multi-agent" in ai_kw:
            kw[ai_kw] = orch_weight
        elif any(e in ai_kw for e in ["eval", "harness", "no-regression", "judge", "ground-truth"]):
            kw[ai_kw] = eval_weight
        else:
            kw[ai_kw] = 1

    for cloud_kw in tech.get("cloud", []):
        kw[cloud_kw] = cloud_weight

    for infra_kw in tech.get("infrastructure", []):
        if infra_kw not in kw:
            kw[infra_kw] = 1

    for data_kw in tech.get("data", []):
        if data_kw not in kw:
            kw[data_kw] = 1

    for eval_kw in tech.get("eval", []):
        if eval_kw not in kw:
            kw[eval_kw] = eval_weight

    return kw, weights


def fetch_jobs(page=1, per_page=50):
    """Fetch a page of jobs from the agentic-engineering-jobs.com API."""
    params = urllib.parse.urlencode({"page": page, "per_page": per_page})
    url = f"{API_BASE}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "agentic-job-finder/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return data.get("data", [])


def is_domain_relevant(job, domain_signals):
    """Check if a job matches the user's domain signals (e.g. agentic AI, data eng, DevOps)."""
    text = " ".join([
        job.get("title", ""),
        job.get("description", ""),
        " ".join(job.get("agenticFrameworks", []) or []),
        " ".join(job.get("aiInfrastructure", []) or []),
    ]).lower()
    return any(sig in text for sig in domain_signals)


def is_remote(job, profile):
    """Check if a job is remote and in the user's target regions."""
    loc_type = (job.get("locationType") or "").lower()
    if loc_type not in ("remote", "hybrid"):
        return False

    countries = job.get("countries") or []
    geo = (job.get("geoRegion") or "").lower()
    location = (job.get("location") or "").lower()
    target_regions = profile.get("remote_regions", ["us", "global", "na"])

    if geo in target_regions:
        return True
    if "US" in countries and "us" in target_regions:
        return True
    if loc_type == "remote" and any(r in location for r in ["remote", "worldwide", "anywhere", "global"]):
        return True

    return False


def is_senior_level(job, profile):
    """Check if a job is at the user's target seniority level."""
    seniority = (job.get("seniority") or "").lower()
    title = (job.get("title") or "").lower()
    levels = profile.get("seniority_levels", ["senior", "staff", "principal", "lead"])
    return any(level in seniority or level in title for level in levels)


def parse_salary(job):
    """Extract salary range from job."""
    smin = job.get("salaryMin")
    smax = job.get("salaryMax")
    currency = job.get("salaryCurrency") or "USD"
    if smin and smax:
        return int(smin), int(smax), currency
    desc = job.get("description") or ""
    matches = re.findall(r'\$(\d{3,3}[\d,]*)\s*[kK]?\s*[-–to]+\s*\$?(\d{3,3}[\d,]*)\s*[kK]?', desc)
    if matches:
        lo = int(matches[0][0].replace(",", "")) * (1000 if len(matches[0][0]) <= 3 else 1)
        hi = int(matches[0][1].replace(",", "")) * (1000 if len(matches[0][1]) <= 3 else 1)
        return lo, hi, currency
    return None, None, currency


def score_job(job, profile, keyword_scores, weights):
    """Score a job on alignment with the user's profile. Returns (score, notes)."""
    text = " ".join([
        job.get("title", ""),
        job.get("description", ""),
        " ".join(job.get("agenticFrameworks", []) or []),
        " ".join(job.get("aiInfrastructure", []) or []),
        " ".join(job.get("techStackTags", []) or []),
    ]).lower()

    score = 0
    notes = []

    for kw, pts in keyword_scores.items():
        if kw in text:
            score += pts

    # Remote bonus
    loc_type = (job.get("locationType") or "").lower()
    if loc_type == "remote":
        score += weights.get("remote", 2)
        notes.append("remote")

    # Comp
    comp_floor = profile.get("comp_floor", 200000)
    smin, smax, _ = parse_salary(job)
    if smax and smax >= comp_floor:
        score += weights.get("comp_above_floor", 1)
        notes.append(f"comp ${smax//1000}K")
    elif smax and smax < comp_floor:
        notes.append(f"comp ${smax//1000}K (below ${comp_floor//1000}K floor)")

    # Seniority
    seniority = (job.get("seniority") or "").lower()
    if "staff" in seniority or "principal" in seniority:
        score += weights.get("staff_or_above", 1)
        notes.append(seniority)

    # Go/RAG requirements
    desc_lower = (job.get("description") or "").lower()
    go_required = "go" in desc_lower and ("required" in desc_lower or "must have" in desc_lower)
    rag_required = "rag" in desc_lower and "required" in desc_lower

    if not go_required:
        score += weights.get("no_go_requirement", 1)
    else:
        score += weights.get("go_required", -2)
        notes.append("Go required")

    if not rag_required:
        score += weights.get("no_rag_requirement", 1)
    else:
        score += weights.get("rag_required", -1)
        notes.append("RAG required")

    # Culture signals (broader than just WLB — includes growth, transparency, autonomy, etc.)
    culture_pos = profile.get("culture_positive_signals", [])
    culture_neg = profile.get("culture_negative_signals", [])
    pos_count = sum(1 for sig in culture_pos if sig in desc_lower)
    neg_count = sum(1 for sig in culture_neg if sig in desc_lower)
    if pos_count > 0 and neg_count == 0:
        score += weights.get("culture_positive", 1)
        notes.append(f"culture+ ({pos_count} signals)")
    elif neg_count > 0:
        score += weights.get("culture_negative", -1)
        notes.append(f"culture- ({neg_count} red flags)")

    # On-call
    if any(sig in desc_lower for sig in ["on-call", "pager", "24/7", "on call"]):
        score += weights.get("on_call", -1)
        notes.append("on-call")

    return score, notes


def assess_viability(job):
    """Assess signals for company viability (default-alive/profitable)."""
    desc = (job.get("description") or "").lower()
    pos = [s for s in VIABILITY_POSITIVE if s in desc]
    neg = [s for s in VIABILITY_NEGATIVE if s in desc]
    notes = []
    if pos:
        notes.append(f"viability+ ({', '.join(pos[:3])})")
    if neg:
        notes.append(f"viability- ({', '.join(neg[:3])})")
    if not pos and not neg:
        notes.append("viability: unknown (needs web research)")
    return len(pos) - len(neg), notes


def assess_product_substance(job):
    """Assess signals for agentic substance (built something real vs hype)."""
    desc = (job.get("description") or "").lower()
    pos = [s for s in PRODUCT_SUBSTANCE_POSITIVE if s in desc]
    neg = [s for s in PRODUCT_SUBSTANCE_NEGATIVE if s in desc]
    notes = []
    if pos:
        notes.append(f"substance+ ({', '.join(pos[:3])})")
    if neg:
        notes.append(f"substance- ({', '.join(neg[:3])})")
    if not pos and not neg:
        notes.append("substance: unknown")
    return len(pos) - len(neg), notes


def get_apply_url(job):
    """Extract the best apply URL from a job."""
    methods = job.get("applyMethods") or []
    for m in methods:
        if m.get("type") == "url" and m.get("value"):
            return m["value"]
    slug = job.get("slug")
    if slug:
        return f"https://agentic-engineering-jobs.com/jobs/{slug}"
    return ""


def scan(profile, pages=5, top=3, min_score=8):
    """Main scan function. Returns list of top matches."""
    keyword_scores, weights = build_keyword_scores(profile)
    domain_signals = profile.get("domain_signals", profile.get("agentic_signals", []))
    all_jobs = []
    seen_companies = set()
    results = []

    for page in range(1, pages + 1):
        try:
            jobs = fetch_jobs(page=page, per_page=50)
            if not jobs:
                break
            all_jobs.extend(jobs)
        except Exception as e:
            print(f"WARN: Failed to fetch page {page}: {e}", file=sys.stderr)
            break

    for job in all_jobs:
        company = (job.get("companyName") or "").strip()
        if not company or company.lower() in seen_companies:
            continue
        if not is_domain_relevant(job, domain_signals):
            continue
        if not is_remote(job, profile):
            continue
        if not is_senior_level(job, profile):
            continue

        seen_companies.add(company.lower())
        score, notes = score_job(job, profile, keyword_scores, weights)
        if score < min_score:
            continue

        viability_score, viability_notes = assess_viability(job)
        substance_score, substance_notes = assess_product_substance(job)
        smin, smax, currency = parse_salary(job)

        results.append({
            "company": company,
            "title": job.get("title", ""),
            "location": job.get("location", ""),
            "location_type": job.get("locationType", ""),
            "seniority": job.get("seniority", ""),
            "salary_min": smin,
            "salary_max": smax,
            "currency": currency,
            "apply_url": get_apply_url(job),
            "posted_at": job.get("postedAt", ""),
            "score": score,
            "notes": notes,
            "viability_heuristic": {
                "keyword_match_count": viability_score,
                "matched_keywords": viability_notes,
                "warning": "KEYWORD COUNT ONLY — not a viability assessment. These are JD-text keyword matches (e.g. 'revenue', 'series c'). The inference layer must web-search the company for actual funding/revenue/profitability data.",
            },
            "product_substance_heuristic": {
                "keyword_match_count": substance_score,
                "matched_keywords": substance_notes,
                "warning": "KEYWORD COUNT ONLY — not a substance assessment. These are JD-text keyword matches (e.g. 'production', 'shipped'). The inference layer must verify via web research.",
            },
            "moat": {
                "assessment": "NOT DETERMINISTIC — requires inference. Web-search the company for unique data, domain expertise, regulatory moat, or orthogonal positioning vs larger competitors.",
            },
            "agentic_frameworks": job.get("agenticFrameworks", []),
            "ai_infrastructure": job.get("aiInfrastructure", []),
            "tech_stack": job.get("techStackTags", []),
            "description_snippet": (job.get("description") or "")[:500],
        })

    results.sort(key=lambda r: (r["score"], r.get("salary_max") or 0), reverse=True)
    return results[:top]


def main():
    parser = argparse.ArgumentParser(description="Scan agentic AI job boards for high-alignment remote roles")
    parser.add_argument("--profile", default=None, help="Path to profile config (default: profile.json or profile.example.json)")
    parser.add_argument("--pages", type=int, default=5, help="API pages to fetch (default: 5)")
    parser.add_argument("--top", type=int, default=3, help="Results to return (default: 3)")
    parser.add_argument("--min-score", type=int, default=8, help="Minimum alignment score (default: 8)")
    args = parser.parse_args()

    # Find profile file
    profile_path = args.profile
    if not profile_path:
        for candidate in ["profile.json", "profile.example.json"]:
            if os.path.exists(candidate):
                profile_path = candidate
                break
    if not profile_path:
        print("ERROR: No profile found. Create profile.json (see profile.example.json) or pass --profile PATH", file=sys.stderr)
        sys.exit(1)

    profile = load_profile(profile_path)
    results = scan(profile, pages=args.pages, top=args.top, min_score=args.min_score)

    if not results:
        print(json.dumps({"matches": [], "message": "No matches found. Try lowering --min-score or increasing --pages."}, indent=2))
        return

    output = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile.get("name", "unknown"),
        "pages_scanned": args.pages,
        "top_results": results,
        "note": "DETERMINISTIC OUTPUT — scores are keyword counts, not assessments. Cross-reference against your job tracker (Notion/spreadsheet) to deduplicate. Then the inference layer must web-search each candidate for the three verification checks (viability, product substance, moat) before presenting."
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()