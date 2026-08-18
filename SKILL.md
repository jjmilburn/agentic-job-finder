---
name: agentic-job-finder
description: >-
  Scan job boards for high-alignment remote roles matching a user's tech profile.
  Two-layer architecture: a deterministic scanner (keyword matching, scoring) produces
  candidates, then the inference layer (agent/human) verifies viability, product
  substance, and defensible moat via web research. The scanner output is explicitly
  labeled as keyword counts, not assessments.
---

# Agentic Job Finder

Two-layer architecture. See README.md for full documentation.

## Layer 1: Deterministic scanner (run the script)

```bash
python3 scan_jobs.py --profile profile.json --top 10 --min-score 8
```

**What it does (all deterministic — keyword matching, no AI/LLM):**
- Fetches jobs from agentic-engineering-jobs.com API
- Filters for remote + senior/staff + domain relevance (your `domain_signals`)
- Scores on tech profile alignment (your `tech_stack` keywords)
- Flags culture signals (your `culture_positive_signals` / `culture_negative_signals`)
- Extracts heuristic keyword signals for viability and product substance

**What it does NOT do:**
- Does NOT assess company viability (keyword "revenue" in JD ≠ profitable)
- Does NOT verify product substance (keyword "production" in JD ≠ product is live)
- Does NOT assess moat (requires understanding the company's positioning)
- Does NOT decide which jobs to apply to

The output fields `viability_heuristic` and `product_substance_heuristic` are **keyword counts with explicit warnings**, not assessments. The `moat` field is flagged as `NOT DETERMINISTIC — requires inference`.

## Layer 2: Inference (agent performs web research)

After the scanner produces candidates:

1. **Deduplicate** against the user's job tracker (Notion MCP query, spreadsheet, etc.)
2. **Verify viability** — web-search each company for funding stage, revenue, profitability, customer traction
3. **Verify product substance** — web-search for evidence of a real, deployed product with named customers
4. **Assess moat** — reason about the company's defensible position vs larger competitors
5. **Present** only companies that pass all three verifications

Each verification has PASS/FAIL/FLAG criteria documented in README.md.

## Why two layers?

Mixing keyword matching with LLM-based assessment in the same tool produces results that are non-reproducible, non-debuggable, and falsely confident. By keeping the scanner deterministic and the verification in the inference layer, the system is reproducible, debuggable, and honest about what it knows vs what needs research.

## Profile configuration

`profile.json` controls the deterministic layer. Key fields:

- **`domain_signals`** — keywords that mark a job as relevant to your domain
- **`culture_positive_signals`** — keywords indicating a culture you want (transparency, autonomy, async, psychological safety)
- **`culture_negative_signals`** — keywords indicating a culture you don't want (grind, stack ranking, politics)
- **`tech_stack`** — your languages, cloud, infrastructure, AI tools — scored on alignment
- **`scoring_weights`** — points for each signal type
- **`comp_floor`** — minimum salary to not flag as below floor
- **`seniority_levels`** / **`remote_regions`** — filter dimensions