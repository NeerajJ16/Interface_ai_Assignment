# Approach

A rules-based knowledge system. It needs no API keys and makes no network calls; answers take about 0.1 s.

## How it works

1. **Versioned store** (`solution/store.py`). Every page of every snapshot is kept, so questions with an `as_of` date are answered from the newest snapshot taken on or before that date.
2. **Chunk index** (`solution/index.py`). Each snapshot is cut into facts: one per table row (with its section heading and column names, so tiers stay attached to their product), one per prose paragraph, one per branch-locator entry, and one per announced lobby / drive-up schedule.
3. **Answering** (`solution/engine.py`). The question is matched against one snapshot's chunks. Rare words weigh more, phrase matches add a bonus, and proper nouns (Forbes, Galena, Visa) are boosted. Qualifiers in the question pick the row: term (60-month), model year (2025 falls in the 2024-27 band), loan amount or balance (the tier that contains it), year term (30-year). A chunk must contain the kind of evidence the question asks for (a rate for rate questions, a time for hours, an address for addresses, a number next to the noun for "how many").
4. **Direct routes** (`solution/routes.py`). A few question types are answered from the exact place the site states them: "what link / how do I join" use a table of every link with its anchor text and page authority; contact-detail updates use the Contact page; membership eligibility combines the live-or-work rule with the counties list.
5. **Conflicts** (`solution/conflicts.py`). The same fact is compared across pages and across snapshots, by number value. Different tiers, terms and products are never compared with each other.

## What counts as "current"

- **The rate sheet wins.** If the same row appears on several pages of the newest snapshot, the page with the highest authority supplies the value: `/rates` and `/business-rates` (100), official product pages (80), core pages (70), landing pages (50), calculators (35), newsroom and blog (15-20), downloadable files (10). Stale copies on calculators and landing pages therefore lose.
- **A page copied forward from an old crawl is penalised** when its own download date is older than its snapshot.
- **Claims that drift** (for example the branch count in press-release boilerplate) are resolved by the newest dated document.
- **Model-year bands** are matched by position in the table, because the labels roll forward each year (2023-26 becomes 2024-27).
- **Honest refusals.** If no chunk covers enough of the question, or nothing contains the evidence it needs, the answer is "I don't know" with `confident=False` and no numbers.

## Decisions and why

- **Rules, not a language model.** The errors this task punishes come from picking the wrong page or tier, which authority ranking and qualifier matching handle exactly. Rules also give identical answers on every run (consistency) and answer in about 0.1 s (speed), and they copy rate values straight from the source row instead of paraphrasing them.
- **One snapshot per question.** Each snapshot is a full copy of the site, so mixing snapshots would mix old and new values. We search the newest eligible snapshot only.
- **Authority over recency for the same fact.** When two pages in the same snapshot disagree, the official rate sheet beats landing pages and calculators, even if the landing page looks newer.
- **Refuse rather than guess.** A rate question needs a chunk that states a rate (a number next to a rate word). Caps such as "adjusts up to 2%" do not count, so a construction-loan rate question is refused.
- **Direct routes only where the site has one clear answer.** Link, contact and eligibility questions are matched by pattern so they are not lost among unrelated prose that merely shares words.
- **Conflicts are real disagreements.** We list a conflict only when the same fact (same product, tier, term and audience) has different values on different pages, or an official value changed between snapshots. The winner is the newest official value.

## Known limits

- Questions whose gold answer comes from an old article (for example the 2023 count of volunteer-time-off users) lose to newer articles that report a different figure.
- Fact matching across snapshots depends on stable row labels; heading text drift is handled, but a fully renamed product would appear as a new fact.

## API keys

None needed. Only the Python standard library is used.

## Helper scripts (`tools/`)

- `show_misses.py` lists practice questions below full score, with our answer.
- `why.py "question"` shows the top-ranked chunks for a question.
- `show_conflicts.py` prints every conflict reported.