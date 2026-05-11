# Vision & Use Cases

## Vision

A private, local-first recipe brain that knows:

- **Every recipe I care about** — scraped from trusted Swiss sites, plus my own creations
- **What's on sale this week** — current promotions at Migros, Coop, Denner, TopCC
- **What I've cooked lately** — so it can rotate, not repeat
- **What's in the fridge / pantry** — so suggestions are actionable tonight
- **What pairs with what wine** — via cellarbrain MCP

…and answers natural-language meal questions in seconds, without me browsing
five recipe sites at 18:30 with a hungry household.

## Primary End-User Use Cases

Each use case is phrased as the question the user actually asks the assistant.

### UC-1 — "What can I cook tonight with what's in the fridge?"

**Inputs:** rough pantry/fridge inventory (manual list, photo, or running state).
**Output:** 2–5 recipes ranked by ingredient coverage, time, and recency.

> *"I have chicken thighs, leeks, cream and rice. 30 minutes max. Suggest 3 options."*

### UC-2 — "Rotate something I haven't cooked in a while"

**Inputs:** cook log (last cooked date per recipe).
**Output:** recipes I rated ≥ 4★ but haven't made in N months.

> *"Surprise me with something I loved but forgot about."*

### UC-3 — "What goes with this wine?"

**Inputs:** wine name or style → cellarbrain MCP (`pair_wine` reversed).
**Output:** recipes whose food tags match the wine's pairing profile.

> *"I'm opening a Barbera d'Alba 2019. What should I cook?"*
>
> → recipebrain queries cellarbrain for the wine's food-pairing tags
> (e.g. `red-meat`, `tomato-sauce`, `aged-cheese`, `mushroom`),
> then returns matching recipes from my collection.

### UC-4 — "Something fancy with duck"

**Inputs:** ingredient + style/occasion filter.
**Output:** recipes tagged `duck` + `dinner-party` / `advanced` / `restaurant-style`.

> *"Friends coming Saturday. Something impressive with duck breast."*

### UC-5 — "Something easy"

**Inputs:** difficulty + time filter.
**Output:** recipes tagged `easy`, ≤ 30 min total, ≤ 8 ingredients.

> *"I'm tired. One pan, under 30 min, kid-friendly."*

### UC-6 — "Plan a menu around this week's promotions"

**Inputs:** current promotion feeds (Migros, Coop, Denner, TopCC).
**Output:** recipes whose key ingredients are on discount this week, with
estimated savings and shopping list grouped by store.

> *"Meal plan for the week using what's on sale."*

### UC-7 — "Add my own recipe"

**Inputs:** free-form text, photo of a handwritten card, or a URL to a non-supported site.
**Output:** structured recipe stored in my collection, taggable, searchable, pair-able.

### UC-8 — "Scale and shop"

**Inputs:** chosen recipe(s) + number of guests.
**Output:** scaled ingredient list, deduplicated across recipes, grouped by store
section, with current promotion prices where available.

### UC-9 — "What did we eat last week?"

**Inputs:** cook log.
**Output:** simple history view — for variety analysis, dietary tracking, or
remembering which recipe was *that good* one on Tuesday.

### UC-10 — "Pair this dish with a wine I own"

**Inputs:** chosen recipe → cellarbrain MCP `pair_wine`.
**Output:** wines from my cellar that match, sorted by drinking-window readiness.

> The natural complement to UC-3, closing the loop with cellarbrain.

## Non-Goals (for v1)

- ❌ Nutritional analysis / macro tracking
- ❌ Calorie counting
- ❌ Multi-user sharing / cloud sync
- ❌ Mobile app (MCP via desktop chat client is enough for v1)
- ❌ Ordering groceries online
- ❌ Auto-detecting fridge contents (image recognition / smart-fridge integration)

## User Persona

Single household, Switzerland, German-speaking region.
Cooks 4–6 dinners/week at home. Owns cellarbrain. Comfortable with a desktop
LLM chat client (the MCP host). Values privacy — recipe collection and shopping
data stay local.
