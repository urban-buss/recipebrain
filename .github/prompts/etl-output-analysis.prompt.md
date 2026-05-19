---
description: "Deep-dive analysis of ETL output Parquet data after a new version run. Reads all Parquet files, computes statistics, identifies data quality issues, and writes a structured analysis doc in analysis/"
agent: agent
argument-hint: "output folder path (e.g. output_v0.0.12)"
---
# ETL Output Data Analysis

Perform a comprehensive, data-driven analysis of the ETL output in the specified folder. **Actually query and inspect the data** — do not make assumptions. Cross-reference findings with source code when root causes are unclear.

## Inputs

The user will provide:
- The output folder path (e.g. `output_v0.0.12`)
- The ETL version number
- Optionally: the command used, run duration, or other context

## Analysis Process

### Phase 1: Inventory & Schema Validation

1. List all `.parquet` files in the output folder
2. For each file, record: row count, file size, column names/types
3. Verify schemas match expectations from `src/recipebrain/writer.py` (`SCHEMAS` dict)
4. Note any empty tables and whether that's expected

### Phase 2: Structural Integrity

Run these checks by loading the Parquet files (use Python/DuckDB in terminal):

- **Referential integrity**: All foreign keys in child tables (recipe_ingredients, recipe_steps, recipe_images, recipe_tags) reference valid parent rows
- **Uniqueness**: `content_hash`, `source_url`, `source_external_id` in recipes should be unique
- **Required fields**: No NULLs or empty strings in required columns (title, language, source_url, description)
- **Duplicates**: Check for duplicate scrapes (same source_url appearing twice)

### Phase 3: Data Quality Deep-Dive

For each major table, compute distributions and identify anomalies:

#### recipes table
- Source distribution (which sources produced data, how many each)
- Language distribution
- Time fields: `prep_minutes`, `cook_minutes`, `total_minutes` — check for the known doubling bug (prep == cook), compute percentiles, find outliers
- Classification fields: `difficulty`, `cuisine`, `course`, `taste_profile`, `weight_class`, `primary_protein`, `cooking_method` — NULL rates and value distributions
- `dietary_flags`: distribution, cross-validate against resolved ingredients (e.g. meat recipes should NOT be vegan)
- `food_groups`: empty rate, value distribution
- `computed_tags`: redundancy check against scalar fields
- Servings distribution
- Description length stats

#### recipe_ingredients table
- Total rows, per-recipe stats (min/max/avg/median)
- **Resolution rate**: % of rows with non-NULL `ingredient_id`
- Top unresolved `raw_text` values (grouped and counted)
- Categorize unresolved items by failure type (missing catalogue entry, parsing failure, non-food items)
- `group_label` population rate
- Quantity/unit extraction success rate

#### ingredients table (catalogue)
- Size and category distribution
- Compare against previous version if available

#### recipe_steps table
- Per-recipe step counts (min/max/median)
- Text length stats
- Empty/very short steps

#### recipe_images table
- Images per recipe
- `local_path` population rate (download success)
- Caption population rate

#### recipe_tags / tags tables
- Tag coverage: % of recipes with at least one tag
- Per-recipe tag count stats
- Tag distribution by facet

### Phase 4: Comparison with Previous Version

If a prior analysis doc exists in `analysis/`, compare key metrics:
- Recipe count change
- Ingredient resolution rate change
- Classification accuracy change
- New issues vs. resolved issues
- Any regressions

Additionally:
- **Git history**: Review commits since the last ETL version tag/release to understand what code changes were made (use `git log --oneline` between version tags)
- **Resolved issues**: Check `issues/_resolved/` for issues that were fixed since the last version — verify whether the fixes actually show improvement in the data
- **Regression check**: For each resolved issue, confirm the fix is reflected in the new output (e.g. if a time-doubling bug was fixed, verify prep != cook in the new data)

### Phase 5: Root Cause Investigation

For any anomalies or quality issues found:
1. Look at the relevant source code (`src/recipebrain/`) to understand why
2. Check `transform.py` for classification logic
3. Check the adapter code for parsing logic
4. Check `normalise.py` and `ingredients.py` for resolution logic
5. Reference known issues in `issues/` folder

## Output Document

Write the analysis as `analysis/NN-etl-vX.Y.Z-output-data-analysis.md` where:
- `NN` is the next sequential number in the `analysis/` folder
- `X.Y.Z` is the ETL version

### Document Structure

```markdown
# ETL vX.Y.Z Output Deep Analysis

**Run command:** `<command>`
**Date:** <date>
**Analyzed folder:** `<folder>`
**Run duration:** <if known>
**Sources processed:** <list>

---

## Summary

<2-3 sentence executive summary: what worked, what's broken, key metrics>

---

## Dataset Overview

| Table | Rows | Notes |
|-------|------|-------|
| ... | ... | ... |

---

## What Went Well

<Numbered findings with evidence — things that improved or work correctly>

---

## What Went Wrong

### Finding N: <Title> [severity]

**Observation:** <what the data shows>
**Pattern:** <quantified breakdown>
**Root cause:** <code reference or hypothesis>
**Impact:** <downstream effects>
**Code reference:** <file:line if applicable>

---

## Quantified Quality Scorecard

| Dimension | Score | Rationale |
|-----------|-------|-----------|
| Schema conformance | ✅/⚠️/❌ % | ... |
| ... | ... | ... |

---

## Recommendations (Prioritized)

### P0 — Critical Fixes
### P1 — High Impact
### P2 — Medium Impact
### P3 — Low Impact / Monitoring

---

## Appendix: Data Distributions

<Statistical tables for time fields, top ingredients, course distribution, etc.>

---

## Related Issues

<Links to issues/ files that relate to findings>
```

## Technical Approach

Use Python with DuckDB or PyArrow to query Parquet files. Example setup:

```python
import duckdb
con = duckdb.connect()
con.execute("SELECT * FROM read_parquet('output_folder/recipes.parquet')")
```

Run queries in the terminal to gather real data. Do NOT fabricate statistics.

## Key Principles

- **Data over assumptions**: Every claim must be backed by an actual query result
- **Quantify everything**: NULL rates, percentiles, distributions — not "some" or "many"
- **Root cause, not symptoms**: When something is wrong, trace to the code that caused it
- **Compare to previous**: Highlight regressions and improvements vs. prior versions
- **Actionable findings**: Each issue should point to a fix or next investigation step
- **Cross-validate**: Check classifications against raw data (e.g. does a "vegan" recipe actually contain meat ingredients?)
