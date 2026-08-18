# Agentic Job Finder

Scan job boards for high-alignment remote roles matching your tech profile. Two-layer architecture: a deterministic scanner that filters and scores, followed by an inference layer that verifies viability, product substance, and defensible moat.

## Architecture: deterministic vs inference

This tool deliberately separates what can be done deterministically (keyword matching, scoring) from what requires inference (web research, qualitative judgment). The boundary is explicit and should not be blurred.

### Layer 1: Deterministic scanner (`scan_jobs.py`)

Pure keyword matching. No AI, no LLM, no judgment. Fast, reproducible, debuggable.

What it does (all deterministic):
- Fetches jobs from the [agentic-engineering-jobs.com](https://agentic-engineering-jobs.com) API (~1500 jobs)
- Filters for: remote (your region), senior/staff/principal level, domain relevance (your `domain_signals` keywords)
- Scores each job on alignment with your tech profile (keyword counting against your `tech_stack` config)
- Flags culture signals (keyword counting against your `culture_positive_signals` / `culture_negative_signals`)
- Extracts heuristic keyword signals for viability ("revenue", "series c", "enterprise customers" appear in the JD) and product substance ("production", "shipped", "real users" appear in the JD)

What it does NOT do:
- It does not assess company viability — it counts keywords. "Revenue" in a JD doesn't mean the company is profitable.
- It does not verify product substance — it counts keywords. "Production" in a JD doesn't mean the product is live.
- It does not assess moat — this requires understanding the company's positioning, which cannot be done from a JD.
- It does not decide which jobs to apply to — it produces a scored, filtered candidate list for the inference layer.

The output fields `viability.heuristic_signals` and `product_substance.heuristic_signals` are **keyword counts, not assessments**. They exist to tell the inference layer where to start looking, not to replace web research.

### Layer 2: Inference layer (the agent / human reviewer)

Requires reasoning, web research, and qualitative judgment. Cannot be automated with keywords.

What it does:
- **Deduplicates** the scanner output against the user's job tracker (Notion pipeline, spreadsheet, etc.)
- **Verifies viability** — web-searches the company for funding stage, revenue, customer traction, profitability, layoff history
- **Verifies product substance** — web-searches for evidence of a real, deployed product with named customers
- **Assesses moat** — reasons about the company's defensible position against larger competitors (unique data, domain expertise, orthogonal positioning, regulatory moat, distribution moat)
- **Decides which jobs to present** — applies judgment about which gaps are acceptable, which companies pass all three verifications, and which are worth the user's time

The three verification frameworks (viability, product substance, moat) are documented below. They are **instructions for the inference layer**, not features of the scanner.

### Why this separation matters

If the scanner tried to assess viability or substance (e.g., by calling an LLM to "rate" the JD), the results would be:
1. **Non-reproducible** — the same JD would score differently on each run
2. **Non-debuggable** — you can't inspect why an LLM gave a score
3. **Falsely confident** — a "viability score" from keyword matching looks like an assessment but is just "the JD mentions 'Series C'"

By keeping the scanner deterministic and the verification in the inference layer, the system is:
- **Reproducible** — same input, same output, every time
- **Debuggable** — you can see exactly which keywords triggered which scores
- **Honest** — the heuristic signals are explicitly labeled as keyword counts, not assessments

## Quick start

```bash
# 1. Copy the example profile and edit it with your tech stack
cp profile.example.json profile.json
# Edit profile.json — set your name, languages, cloud stack, comp floor, domain signals, culture signals

# 2. Run the scanner (deterministic — produces scored candidates)
python3 scan_jobs.py --top 10 --min-score 8

# 3. Deduplicate against your job tracker (Notion, spreadsheet, etc.)
# 4. For each remaining candidate, run the three verification checks (inference layer — web research)
# 5. Apply to the ones that pass all three verifications
```

## Configuration

Create `profile.json` (copy from `profile.example.json`). Key fields:

| Field | What it controls | Layer |
|---|---|---|
| `tech_stack` | Your languages, cloud, AI tools, data stores — scored on alignment | Deterministic |
| `domain_signals` | Keywords that mark a job as relevant to your domain | Deterministic |
| `culture_positive_signals` | Keywords that indicate a culture you want | Deterministic |
| `culture_negative_signals` | Keywords that indicate a culture you don't want | Deterministic |
| `scoring_weights` | Points for each signal type | Deterministic |
| `comp_floor` | Minimum salary to not flag as "below floor" | Deterministic |
| `seniority_levels` | Which levels to include | Deterministic |
| `remote_regions` | Which regions to include | Deterministic |
| `notion.enabled` | Whether to deduplicate against a Notion pipeline | Inference (MCP) |
| `notion.pipeline_collection_id` | Your Notion Pipeline collection ID | Inference (MCP) |

## The three verification checks (inference layer)

These are performed by the agent/human after the scanner produces candidates. They require web research and qualitative judgment — they cannot be automated with keywords.

### 1. Company viability (default-alive or profitable)

**Web-search for:** funding stage, revenue/ARR, customer counts, profitability, layoff history.

- **PASS**: Series C+ with named enterprise customers, OR profitable/default-alive, OR government contract revenue, OR publicly traded.
- **FAIL**: Pre-revenue seed-stage with no named customers and no clear monetization.
- **FLAG**: Series A/B with some traction but unclear path to profitability.

### 2. Product substance (built something real, not hype)

**Web-search for:** product stage, customer evidence, case studies, blog posts showing real deployments.

- **PASS**: Product is live with named customers, JD describes operating/scaling an existing system.
- **FAIL**: Product is a roadmap item, JD says "exploring"/"experimenting", no public product evidence.
- **FLAG**: Early-stage product with real users but small scale (acceptable if the role is about scaling it).

### 3. Defensible moat against bigger competitors

**Web-search for:** unique data, domain expertise, orthogonal positioning, regulatory moat, distribution moat.

- **PASS**: Clear, articulable moat — can explain in one sentence why a larger competitor can't replicate this in 6-18 months.
- **FAIL**: The value proposition is a thin wrapper around a larger company's API — the larger company could ship it as a feature.
- **FLAG**: The moat exists but is narrow or eroding.

**Moat categories to look for:**
- **Unique data agreements**: Proprietary data that competitors can't access
- **Unique domain knowledge**: Deep vertical expertise (healthcare, defense, finance, industrial)
- **Orthogonal positioning**: Value proposition is orthogonal to the big players' strategy (e.g., open-model inference vs. closed-model labs, observability tools vs. model providers, agent governance vs. agent builders)
- **Regulatory/compliance moat**: Operating in regulated environments where bigger competitors won't go (HIPAA, FedRAMP, DoD clearance)
- **Distribution/integration moat**: Embedded in customer workflows that a competitor's API call can't replace
- **Cost/architecture moat**: Structural cost advantage (inference cost optimization, multi-model routing)

## API reference

The scanner uses the [agentic-engineering-jobs.com](https://agentic-engineering-jobs.com) API:

```
GET https://agentic-engineering-jobs.com/api/v1/jobs?page=1&per_page=50
```

Each job object includes: `title`, `companyName`, `location`, `locationType`, `seniority`, `salaryMin`, `salaryMax`, `description`, `applyMethods`, `agenticFrameworks`, `aiInfrastructure`, `techStackTags`, `postedAt`, `slug`.

## License

MIT — do whatever you want with this. Pull requests welcome.