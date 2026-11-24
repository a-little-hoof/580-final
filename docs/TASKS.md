# Provisional local evaluation tasks

These are **draft local candidates**, not confirmed course plugins or completed experiments. Select or import five tasks from the actual available Rush Lab course plugins, and complete the assignment's Task 0 exploration across available models **before developing the compact-output modification**. Adapt these candidates only where the course permits local tasks; document their provenance. Do not present local runs as Rush Lab app runs, or fill missing measurements with estimates.

The proposed custom CLI uses coding tools in the Rush terminal and writes `answer.json`; it currently has no course-plugin broker. Running that CLI in Rush does not, by itself, establish compatibility with course plugins. Actual plugin discovery and integration remain prerequisites to the course evaluation.

## Common execution contract

- Each task exposes a precise prompt and immutable input fixtures in a fresh workspace. The agent may list/read files, execute code, and write its answer using the coding tools available in the chosen harness.
- Both conditions receive the same tools, instructions, fixtures, budgets, and artifact read/search access. Only the presentation of eligible tool output may differ in the later experiment.
- The agent may filter inputs or write scripts that print only a final summary. Never require a full-data dump or forbid an efficient baseline strategy to manufacture a compression benefit.
- All prompts below are drafts. Their file schemas, output schemas, and scope constraints must accompany any instantiated task. All dates are fixed inputs, not the current date.
- Keep `answer.json` as the sole graded output. Compare parsed content, not whitespace or JSON object-key order. Where an array order is specified, enforce it. Reject duplicate JSON keys, missing/extra fields or records, non-finite values, and incorrect types; booleans are not valid integer amounts.

## 1. `small_catalog`: short-output control

**Fixtures:** `catalog.json`, an array of 12 records with unique string `item_id`, string `category`, boolean `in_stock`, nonnegative integer `price_cents`, and ISO date `delivery_date`. At least one item qualifies.

**Draft prompt:**

> From `catalog.json`, select an in-stock item in category `storage` whose delivery date is on or before `2026-12-10`. Choose the lowest price; break ties using the lexicographically smallest item ID. Write `answer.json` as `{"item_id": "...", "price_cents": 0}` with the selected item's actual values. Do not modify the input.

**Validator:** Independently filter and sort the public records, then compare the exact two fields. Check deadline equality, an earlier cheaper ineligible item, an unavailable cheapest item, and price ties. Keep the fixture small enough that its normal display fits the eventual preview budget; this is a negative control where little benefit is expected.

## 2. `invoice_reconciliation`: long structured input

**Fixtures:** `ledger.jsonl`, approximately 600 records with string `transaction_id`, `account_id`, and `currency`; status `posted` or `void`; and signed integer `delta_cents`. Duplicate transaction IDs, when present, repeat an identical record. Currency is part of the grouping key.

**Draft prompt:**

> Reconcile `ledger.jsonl`. Count each transaction ID once, ignore void transactions, and sum `delta_cents` separately for each account and currency. Include every pair with at least one posted transaction, even when its balance is zero. Write `answer.json` as `{"balances": [{"account_id": "...", "currency": "...", "balance_cents": 0}]}`, sorted by account ID and then currency. Do not modify the input.

**Validator:** Deduplicate by ID and independently accumulate posted deltas. Require the complete set of groups and exact signed integer balances. Check identical duplicate transactions, negative adjustments, void transactions, zero balances, and one account with multiple currencies. Conflicting duplicate IDs are outside this task's declared scope and must be rejected by fixture validation.

## 3. `failed_job_audit`: noisy logs and retries

**Fixtures:** `events.jsonl`, several thousand interleaved job events. Each has a unique integer `seq`, string `job_id`, positive integer `attempt`, and event `START`, `ERROR`, or `END`. ERROR events contain `error_code`; END events contain outcome `success` or `failed`. Every attempt has one START and END, every job is finished, and every failed attempt contains an ERROR. Sequence numbers define event order.

**Draft prompt:**

> Audit `events.jsonl`. A job's final attempt is its greatest attempt number. Report only jobs whose final attempt ended in failure. For each, return the final attempt number and the error code from that attempt's earliest ERROR event by sequence number. Exclude failed attempts later recovered by a successful attempt. Write `answer.json` as `{"failed_jobs": [{"job_id": "...", "attempt": 1, "error_code": "..."}]}`, sorted by job ID. Do not modify the input.

**Validator:** Cross-check private generation-time job outcomes against a separate event-state reducer over the public log. Compare exact job membership, attempt numbers, and first error codes. Check recovered retries, multiple errors within an attempt, interleaved jobs, and successful jobs that emitted an earlier error. This evaluates useful error excerpts without treating every error line as a final failure.

## 4. `shipment_join`: several inputs and partial fulfillment

**Fixtures:** `orders.csv` contains unique `order_id`, `customer_id`, positive integer `quantity`, nonnegative integer `unit_price_cents`, ISO `due_date`, and status `open` or `cancelled`. `customers.csv` maps unique customer IDs to regions. `shipments.csv` contains unique shipment IDs, order IDs, and positive integer quantities. All foreign keys resolve, and total shipped quantity never exceeds the order quantity.

**Draft prompt:**

> Join `orders.csv`, `customers.csv`, and `shipments.csv`. Find open orders due strictly before `2026-12-01` with a positive unshipped quantity. For each, compute `outstanding_qty = quantity - total shipped quantity` and `outstanding_value_cents = outstanding_qty * unit_price_cents`. Write `answer.json` with `orders`, containing `order_id`, `region`, `outstanding_qty`, and `outstanding_value_cents`, sorted by order ID; and `region_totals`, containing `region` and summed `outstanding_value_cents`, sorted by region. Include only regions represented by qualifying orders. Do not modify the inputs.

**Validator:** Use independent reference SQL through Python's standard-library `sqlite3` and cross-check generation-time quantities. Require all qualifying orders and exact regional totals. Check no shipment, several partial shipments, complete fulfillment, canceled orders, a due date exactly at the cutoff, and zero-priced outstanding items. A total-only check is insufficient because compensating row errors can preserve totals.

## 5. `policy_resolution`: recover an omitted decisive detail

**Fixtures:** `accounts.json` maps account IDs to regions. `policies.json` is a large array of rules with unique string `rule_id`, scope `global`, `region`, or `account`; matching `scope_id` (`*` for global); ISO `effective_date`; and a `limits` object containing one or both integer fields `daily_limit` and `monthly_limit`. Every requested account has an active global default for both fields. More specific rules may override only one field.

**Draft prompt:**

> Resolve the daily and monthly limits for accounts `acct001`, `acct002`, `acct003`, `acct004`, and `acct005` as of `2026-12-01`. Use only rules effective on or before that date. Resolve each field separately: account rules override region rules, which override global rules. Within the same scope, choose the latest effective date; break remaining ties using the lexicographically greatest rule ID. Write `answer.json` as `{"accounts": [{"account_id": "...", "daily_limit": 0, "daily_rule_id": "...", "monthly_limit": 0, "monthly_rule_id": "..."}]}`, sorted by account ID. Do not modify the inputs.

**Validator:** Independently resolve each field and compare both its value and winning rule ID. Check partial overrides, future rules, cutoff equality, precedence over recency, and date ties. Place one relevant ordinary rule in the middle of the catalog so a head/tail preview omits it. Label this explicitly as an information-recovery stress case in the report; it is not evidence that all workloads have this structure. The agent remains free to query or process the catalog directly.

## Generator and validator boundaries

Use Python's standard library for local fixture generation and private reference checks. A minimal conceptual interface is:

```python
generate(task_id, seed, public_dir) -> private_truth
validate(task_id, public_dir, answer_path, private_truth) -> validation_result
```

Generators, private truth, validators, and expected-answer files must stay outside the filesystem exposed to the agent. A different directory is not sufficient isolation when the agent has unrestricted shell access: use a constrained execution environment that exposes only intended files, and verify that boundary before claiming answers are inaccessible. Never place truth in public metadata, helper scripts, filenames, environment variables, or model feedback. Preserve input hashes and fail validation if fixtures changed.

Develop each validator against hand-worked miniature cases, then compare independently computed references on generated cases. Mutate correct answers to check missing/extra rows, wrong values, wrong provenance, malformed JSON, and boundary cases listed above. Sharing a generator's answer computation as the only validator does not provide an independent correctness check. Guarantees apply only to the explicitly declared input scope, not arbitrary malformed real-world data.

## Selection and evaluation discipline

Perform genuine Task 0 app exploration first, recording each task/model's input tokens, output tokens, cached tokens, outcome, failure details, and latency. Ensure all five final selected tasks have this exploration coverage, then freeze their inputs, rules, and validators before final comparisons. Keep development seeds separate from final fixtures, and state whether final runs repeat one fixture or span multiple fixtures.

Include the short control and an information-recovery stress case alongside representative workloads. Fix fixture sizes for substantive task reasons, not to push one method past a context limit. Preserve efficient agent behavior and report null or negative improvements. Repetitions estimate variability on the selected tasks; they do not turn five tasks into evidence of broad generalization. This document specifies candidate tasks only and does not implement compaction or report experimental results.
