# MCP Tools

The MCP server is the primary interface. The user talks to an LLM chat client
(the MCP host); the LLM calls these tools. All tools are read-only or
append-only — no destructive operations exposed to the LLM.

Naming follows cellarbrain's pattern (snake_case verbs).

## Tool Summary

| # | Tool                       | Kind        | Purpose                                                         |
|---|----------------------------|-------------|-----------------------------------------------------------------|
| 1 | `find_recipe`              | search      | Generic search by text, tag, ingredient, time, course           |
| 2 | `read_recipe`              | read        | Full recipe dossier (Markdown)                                  |
| 3 | `suggest_for_pantry`       | recommend   | Best matches for current pantry/fridge contents                 |
| 4 | `suggest_rotation`         | recommend   | High-rated recipes not cooked recently                          |
| 5 | `suggest_for_wine`         | recommend   | Recipes matching a wine's pairing profile (cellarbrain bridge)  |
| 6 | `suggest_for_promotions`   | recommend   | Recipes whose ingredients are on sale this week                 |
| 7 | `suggest_easy`             | recommend   | Quick weeknight picks                                           |
| 8 | `shopping_list`            | compose     | Scaled, deduplicated shopping list with current prices          |
| 9 | `log_cook`                 | append      | Record a cook event                                             |
| 10| `update_pantry`            | append      | Update pantry hints                                             |
| 11| `add_recipe`               | append      | Ingest an own recipe (Markdown or URL)                          |
| 12| `current_promotions`       | read        | Browse this week's promotions, optionally by ingredient/category|
| 13| `cellar_pairing`           | bridge      | Ask cellarbrain which of *my wines* pair with a chosen recipe   |
| 14| `query_recipes`            | sql         | Validated DuckDB SELECT over the recipe schema (power user)     |
| 15| `server_stats`             | meta        | Counts, last refresh times, source health                       |

All tools handle exceptions and return `f"Error: {exc}"` strings — never raise
across the MCP boundary (cellarbrain pattern).

## Tool Specifications

### 1. `find_recipe`

```python
find_recipe(
    query: str | None = None,           # full-text search across title + description
    must_have: list[str] | None = None, # ingredient keys that MUST be present
    must_not_have: list[str] | None = None,
    tags: list[str] | None = None,      # any-of match
    course: str | None = None,          # main, starter, dessert, ...
    cuisine: str | None = None,
    max_total_minutes: int | None = None,
    difficulty: str | None = None,
    language: str | None = None,
    limit: int = 10,
) -> str
```

**Returns:** ranked list (Markdown table) of recipe summaries with id, title,
total time, difficulty, last cooked, owner rating.

### 2. `read_recipe`

```python
read_recipe(recipe_id: int) -> str
```

Returns the full Markdown dossier for the recipe, including ingredients
(scaled to default servings), steps, image references, source link, cook log,
and any user notes.

### 3. `suggest_for_pantry`

```python
suggest_for_pantry(
    extra_ingredients: list[str] | None = None,  # ad-hoc additions
    missing_ok: int = 2,                          # tolerated missing ingredients
    max_total_minutes: int | None = None,
    limit: int = 5,
) -> str
```

Ranks recipes by `coverage_score = covered / required_excluding_pantry_staples`,
penalised by missing critical ingredients. Pantry staples (salt, pepper, oil)
are configurable and assumed present.

**Example call:** `"weeknight dinner using what's in the fridge"`

### 4. `suggest_rotation`

```python
suggest_rotation(
    min_rating: int = 4,
    not_cooked_in_days: int = 90,
    limit: int = 5,
) -> str
```

> *"Surprise me with something I loved but forgot about."*

### 5. `suggest_for_wine`

```python
suggest_for_wine(
    wine_query: str | None = None,    # free text → resolved via cellarbrain
    wine_id: int | None = None,       # cellarbrain wine id, exact
    pairing_tags: list[str] | None = None,  # bypass cellarbrain, use given tags
    limit: int = 5,
) -> str
```

If `wine_query` or `wine_id` is supplied, recipebrain calls cellarbrain's
`pair_wine` MCP tool to obtain the wine's recommended food-pairing tags, then
searches for recipes whose aggregated `pairing_tags` (from `v_recipe_pairing_tags`)
have the highest overlap.

> *"I'm opening a Barbera d'Alba 2019. What should I cook?"*

### 6. `suggest_for_promotions`

```python
suggest_for_promotions(
    retailer: str | None = None,         # 'migros' | 'coop' | 'denner' | 'topcc'
    min_discount_pct: float = 0.0,
    limit: int = 10,
) -> str
```

Ranks recipes by *value of promoted ingredients consumed* — i.e. recipes that
make heavy use of currently-discounted items. Output includes estimated
shopping cost and savings vs. regular price, grouped by retailer.

> *"Meal plan for the week using what's on sale."*

### 7. `suggest_easy`

```python
suggest_easy(
    max_total_minutes: int = 30,
    max_ingredients: int = 8,
    avoid_recent_days: int = 14,
    limit: int = 5,
) -> str
```

> *"I'm tired. One pan, under 30 min."*

### 8. `shopping_list`

```python
shopping_list(
    recipe_ids: list[int],
    servings_per_recipe: dict[int, int] | None = None,
    deduct_pantry: bool = True,
    group_by: str = "store_section",   # 'store_section' | 'retailer'
) -> str
```

Returns a Markdown shopping list. When `group_by='retailer'`, the list is split
by which retailer currently has the best promotional price for each ingredient.

### 9. `log_cook`

```python
log_cook(
    recipe_id: int,
    cooked_on: str | None = None,   # ISO date; defaults to today
    servings: int | None = None,    # defaults to recipe.servings
    rating: int | None = None,      # 1..5
    notes: str | None = None,
) -> str
```

Append-only. Returns confirmation including new `times_cooked` count.

### 10. `update_pantry`

```python
update_pantry(
    additions: list[dict] | None = None,  # [{"ingredient": "cream-double", "quantity": 250, "unit": "ml"}]
    removals: list[str] | None = None,    # ingredient keys to mark depleted
    location: str = "fridge",
    note: str | None = None,
) -> str
```

Best-effort hint store, not strict accounting.

### 11. `add_recipe`

```python
add_recipe(
    source: str,                  # 'markdown' | 'url' | 'text'
    payload: str,                 # markdown content, URL, or free-form text
    title: str | None = None,     # required when source='text'
    tags: list[str] | None = None,
    review_required: bool = True, # if true, status='draft' until user confirms
) -> str
```

Returns the new `recipe_id` and a structured preview the user can confirm.

### 12. `current_promotions`

```python
current_promotions(
    retailer: str | None = None,
    ingredient: str | None = None,
    category: str | None = None,
    min_discount_pct: float = 0.0,
    limit: int = 50,
) -> str
```

Browse this week's promotions. Useful for "is X on sale anywhere?" queries.

### 13. `cellar_pairing`

```python
cellar_pairing(
    recipe_id: int,
    only_drinking_now: bool = True,
    limit: int = 5,
) -> str
```

Calls cellarbrain's MCP to find wines from the user's actual cellar that pair
with the given recipe. Closes the loop with UC-10.

> *"What of my wines pairs with the lamb shank recipe?"*

### 14. `query_recipes`

```python
query_recipes(sql: str, limit: int = 100) -> str
```

Validated SELECT-only DuckDB query (mirrors cellarbrain's `query_cellar`).
Validator rejects INSERT/UPDATE/DELETE/DROP/CREATE/ALTER/TRUNCATE.

### 15. `server_stats`

```python
server_stats() -> str
```

Returns: total recipes per source, total ingredients, active promotions count,
last scrape per source, last promotion refresh, pantry size, cook events this
month.

## Resources (MCP read-only resource URIs)

In addition to tools, expose:

| URI                                  | Content                                            |
|--------------------------------------|----------------------------------------------------|
| `recipebrain://recipe/{id}`          | Full dossier markdown                              |
| `recipebrain://shopping/{list_id}`   | Last generated shopping list                       |
| `recipebrain://promotions/current`   | This week's promotions, all retailers              |
| `recipebrain://stats`                | Same content as `server_stats`                     |

## Cross-Server Interop with cellarbrain

Two patterns:

1. **Recipebrain calls cellarbrain** (server-side bridge)
   - Used by `suggest_for_wine` and `cellar_pairing`
   - Requires recipebrain to be configured with cellarbrain's MCP endpoint
   - Failure mode: if cellarbrain is unreachable, tools degrade gracefully and
     suggest using `pairing_tags` directly

2. **The MCP host orchestrates both** (client-side)
   - The user's chat client has both servers loaded
   - The LLM chains: cellarbrain → tags → recipebrain → recipes
   - Simpler, no inter-server config; preferred default

Recommendation: ship pattern 2 only in v1. Add pattern 1 if and when needed.

## Tool Safety

- All write tools (`log_cook`, `update_pantry`, `add_recipe`) are append-only or
  best-effort updates — no destructive deletes via MCP
- Any "delete recipe" / "rebuild index" / "wipe pantry" operation is **CLI-only**
- `query_recipes` strictly read-only (cellarbrain `validate_sql` pattern)

## CLI Counterparts

For everything an LLM should *not* do, provide CLI equivalents:

```bash
recipebrain etl                       # full or incremental scrape + promotion refresh
recipebrain etl --source fooby        # one source
recipebrain promotions refresh        # promotions only
recipebrain ingest <file-or-url>      # add own recipe
recipebrain validate                  # FK + schema integrity checks
recipebrain mcp                       # start MCP server
recipebrain reindex                   # rebuild search indexes
recipebrain snapshot                  # manual snapshot before risky ops
```
