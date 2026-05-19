---
description: "Generate structured issue files from ETL analysis findings. Creates one detailed issue file per finding in issues/, ordered by severity, with proper numbering."
agent: agent
argument-hint: "analysis doc path (e.g. analysis/34-etl-v0.0.13-output-data-analysis.md)"
---
# Generate Issue Files from ETL Analysis

After an ETL output analysis has been completed and reviewed, create individual issue files for every finding that needs to be addressed. Each issue gets its own file in the `issues/` folder.

## Inputs

The user will provide:
- The analysis document path (e.g. `analysis/34-etl-v0.0.13-output-data-analysis.md`)
- Optionally: which findings to skip (e.g. informational ones that don't need action)

## Process

### Step 1: Determine Next Issue Number

1. Check `issues/_resolved/` and `issues/_not-an-issue/` for existing files
2. Find the highest existing issue number across all subfolders
3. Start numbering new issues from `highest + 1`

### Step 2: Extract Findings

Read the analysis document and extract all findings from "What Went Wrong" and "Recommendations" sections that represent actionable issues. Skip:
- Purely informational observations (e.g. "duplicate titles are legitimate variants")
- Issues that already exist in `issues/` or `issues/_resolved/` (check by description similarity)

### Step 3: Order by Severity

Sort findings for file creation in this order:
1. **critical** — blocks basic usability or produces incorrect data
2. **high** — significantly degrades data quality or user experience
3. **medium** — limits completeness or causes confusion
4. **low** — nice-to-have improvements

### Step 4: Create Issue Files

For each finding, create `issues/NNN-short-slug.md` with the structure below. Create them **one by one**, confirming each is written before moving to the next.

**IMPORTANT:** New issues ALWAYS go in the root `issues/` folder — never in `issues/_resolved/` or `issues/_not-an-issue/`. Those subfolders are only for issues that have already been triaged or closed.

## Issue File Format

```markdown
# NNN — <Descriptive Title>

**Severity:** critical | high | medium | low
**Component:** <module or subsystem> (e.g. `transform.py`, `ingredient catalogue`, `bettybossi adapter`)
**Reported:** <date>
**Status:** open
**Blocks:** <what downstream features/fields are affected>

## Symptom

<What the data shows — quantified. Include specific numbers from the analysis.>

## Evidence

<Concrete examples from the data. Include:>
- Sample rows or values that demonstrate the problem
- Distribution tables showing the anomaly
- Comparison with expected values

## Root Cause

<Technical explanation of WHY this happens. Reference specific code locations:>
- File path and line numbers where the bug lives
- The logic flow that produces the wrong result
- Why the current code doesn't handle this case

<Include relevant code snippets if they clarify the issue.>

## Downstream Impact

<What other fields, features, or systems are affected by this issue:>
- Which computed fields become unreliable
- Which MCP tools return wrong results
- Which user-facing filters break

## Proposed Fix

<Concrete implementation guidance:>
1. Step-by-step description of the code change needed
2. Where to make the change (file + function)
3. Edge cases to handle

## Expected Outcome After Fix

<What the data should look like once fixed:>
- Target metric (e.g. "ingredient resolution rate should reach ≥92%")
- How to verify the fix worked (specific query or check)

## Test Cases

<Specific test scenarios to add:>
- Input → expected output for the happy path
- Edge cases that must be covered
- Regression test for the original bug

## Related

- Analysis: `<path to analysis doc>`
- Prior issues: `<related issue numbers if any>`
```

## Key Principles

- **Self-contained**: Each issue file must contain enough detail to be addressed in a fresh session without needing the original analysis doc open
- **Quantified**: Always include specific numbers, percentages, row counts — never "some" or "many"
- **Code-referenced**: Point to exact files, functions, and line numbers where changes are needed
- **Testable**: Include concrete test cases so the fix can be verified
- **No duplicates**: Skip findings that already have an open or resolved issue — reference the existing issue instead
- **Examples**: Include sample data (recipe titles, raw_text values, etc.) that illustrate the problem

## After Completion

Once all issue files are created, output a summary table:

```markdown
| # | Title | Severity | Component |
|---|-------|----------|-----------|
| 062 | ... | critical | ... |
| 063 | ... | high | ... |
```

And note any findings from the analysis that were intentionally skipped (already tracked, informational, or not actionable).
