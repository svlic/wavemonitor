# HANDOFF: Multi-level support/resistance freeze

Session checkpoint for a new agent. Resume from this file plus the git working tree. Do not treat `.omo/plans/` as implementation authority; current code and `backend/API_CONTRACT.md` win.

---

## 1. Goal

Finish a **tests-first rewrite** so one instrument can store multiple support and resistance levels.

- Persist levels as JSON arrays (`supports`, `resistances`) on `Instrument`.
- At evaluation time, pick **one** nearest pair with `nearest_pair(...)`, then keep `evaluate_rules` scalar on that pair.
- Alert snapshots (`AlertEvent.support` / `AlertEvent.resistance`) stay scalar — they record the pair that fired, not the full ladder.
- This freeze session documents the half-wired state. **Do not implement remaining production wiring from this file unless a later session explicitly asks.**

---

## 2. Git HEAD

- Repo: `/opt/ocode/wavemonitor`
- HEAD: `29d0db8` `fix(persistence): load legacy alert_mode values in ORM`
- Working tree (uncommitted): 6 files, `+328 / −91`

```
 M backend/src/wavemonitor_backend/support_resistance.py
 M backend/tests/test_api_instruments.py
 M backend/tests/test_db_migrations.py
 M backend/tests/test_models.py
 M backend/tests/test_rule_persistence.py
 M backend/tests/test_support_resistance.py
?? uv.lock
```

- Ignore untracked `uv.lock`. It is unrelated.
- Nothing multi-level is committed. The committed product is still scalar S/R plus live fixed-drawdown.

---

## 3. Committed product (HEAD)

Scalar support/resistance plus fixed-drawdown, fully wired:

- `Instrument.support` / `Instrument.resistance`: nullable `NUMERIC(24, 10)`
- `alert_mode`: `static` | `fixed_drawdown`
- Fixed-drawdown: `high_water`, `fixed_drawdown`; support derived as `high_water - fixed_drawdown`; client must not send support
- SQLite rebuild in `db.py` still copies scalar columns via `INSTRUMENT_COLUMNS`
- HTTP create/replace still documents scalar `support` / `resistance` in `backend/API_CONTRACT.md`
- Frontend Zod + form still send/parse scalar strings
- `evaluate_and_persist_rules` passes `instrument.support` / `instrument.resistance` straight into `evaluate_rules`

This committed stack is internally consistent. The uncommitted tests are not.

---

## 4. Uncommitted diff (half-wired rewrite)

**Only production change:** `backend/src/wavemonitor_backend/support_resistance.py`

- Added `nearest_pair(supports, resistances, price) -> tuple[Decimal | None, Decimal | None]`
- `validate_instrument_levels` now takes sequences: `supports: Sequence[Decimal]`, `resistances: Sequence[Decimal]`
- Static: at least one level; every level `> 0`; if both sides present, `max(supports) < min(resistances)`
- Fixed-drawdown: every support (if any) must equal derived support; `len(resistances) <= 1`; derived support still `<` that resistance
- `levels_for_alerts`, `derived_support`, `lift_high_water` unchanged (still scalar)

**Tests rewritten first** (5 files) to expect arrays / JSON columns / nearest-pair persist. Production model, schema, db, API, and frontend were **not** updated. The tree is therefore inconsistent: running pytest against current models will fail (e.g. `Instrument(..., supports=[...])` hits unknown fields; `validate_instrument_levels(support=..., resistance=...)` no longer matches the new signature).

Do **not** run the full suite as a freeze check. It is expected to fail until the remaining wiring lands.

---

## 5. Production vs tests mismatch

| Layer | Production (on disk, except `support_resistance.py`) | Uncommitted tests expect |
| --- | --- | --- |
| Domain | `Instrument.support` / `.resistance` scalars | `instrument.supports` / `.resistances` as `list[Decimal]` |
| Validation call | `_assert_rule_contract` still calls `validate_instrument_levels(support=..., resistance=...)` | Sequence kwargs `supports=` / `resistances=` |
| Schema / API | `InstrumentRequest` / `InstrumentResponse` scalars | JSON arrays of decimal strings; empty list `[]` means unset side |
| Persistence | `evaluate_and_persist_rules` uses `instrument.support` / `.resistance` | Call `nearest_pair` first; persist snapshot of pair 98/130 for levels `["90","98"]` / `["130","150"]` at price 100 |
| SQLite | columns `support`, `resistance` | columns `supports`, `resistances` (JSON text); old scalar columns gone after migrate |
| Frontend | Zod `support` / `resistance` optional strings | not rewritten yet |

`app.py` itself has almost no level fields (routes delegate to `api.py`). Scalar create/update/response mapping lives in `api.py`.

---

## 6. `nearest_pair` / validation contract (locked by tests)

### `nearest_pair`

```python
def nearest_pair(
    supports: Sequence[Decimal],
    resistances: Sequence[Decimal],
    price: Decimal,
) -> tuple[Decimal | None, Decimal | None]:
    """Pick the greatest support below price and the least resistance above it."""
    below = tuple(level for level in supports if level < price)
    above = tuple(level for level in resistances if level > price)
    return (max(below) if below else None, min(above) if above else None)
```

Rules (strict inequality):

- Support = greatest level **strictly `<` price**, else `None`
- Resistance = least level **strictly `>` price**, else `None`
- Levels on the price itself are ignored (not below, not above)
- Input order does not matter (tests pass unsorted tuples)
- Example: supports `(90, 98, 80)`, resistances `(120, 105, 130)`, price `100` → `(98, 105)`
- Example: supports `(100, 110, 90)`, resistances `(100, 95, 120)`, price `100` → `(90, 120)`
- Example: supports `(100, 110)`, resistances `(90, 100)`, price `100` → `(None, None)`

`evaluate_rules` stays scalar. Persistence must select the pair **before** calling it.

### `validate_instrument_levels`

Static:

- `high_water` / `fixed_drawdown` must be unset
- `not supports and not resistances` → `"at least one of support or resistance must be set"`
- each level `> 0`
- if both sides non-empty: `max(supports) >= min(resistances)` → `"support must be less than resistance"`
- overlapping ladders are rejected even if some inner pair would be valid (API test: supports `["90","110"]` vs resistances `["105","130"]`)

Fixed-drawdown:

- `high_water` and `fixed_drawdown` required; drawdown `> 0`
- derived support = `high_water - fixed_drawdown` and must be `> 0`
- any provided support must equal derived (`"support is derived"`)
- `len(resistances) > 1` → `"fixed_drawdown accepts at most one resistance"`
- optional single resistance must be `> 0` and strictly above derived support

Thresholds (still on `Instrument` / `InstrumentRequest`, not inside `validate_instrument_levels`):

- `near_support_threshold` required when support is set (including derived); must be `(0, 1)`
- `risk_reward_threshold` required when **both** a support and a resistance are set; must be `> 0`
- support-only → resistances `[]`, `risk_reward_threshold` null
- resistance-only → supports `[]`, `near_support_threshold` null

Empty-side encoding in JSON/API: `[]`, not `null`.

---

## 7. Remaining backend scalar sites

Change these in a later session, in this order. Line numbers are from the freeze snapshot (HEAD + uncommitted `support_resistance.py` only).

### `models.py`

- `RuleDecimalMixin.parse_optional_level` still validates `"support"` / `"resistance"` as scalars (lines ~68–78)
- `Instrument.support` / `Instrument.resistance` scalar fields (122–123)
- `_needs_rule_field_coercion` / `_coerce_rule_fields` coerce scalars
- `_derive_fixed_drawdown_support` writes `self.support`
- `_assert_rule_contract` still calls `validate_instrument_levels(support=self.support, resistance=self.resistance, ...)` — **this is already a TypeError against the uncommitted validator signature**
- `AlertEvent.support` / `.resistance` stay scalar (alert snapshot). Do not array those.

Target shape (from tests): `instrument.supports == [Decimal("140"), Decimal("150")]`; fixed-drawdown stores `supports == [Decimal("95000")]` derived; reject extra resistances in drawdown mode.

### `schemas.py`

- `InstrumentRequest` / `InstrumentResponse`: `support: Decimal | None`, `resistance: Decimal | None` (~109–114, 167–168)
- `InstrumentRequest.validate_rule_contract` still calls scalar `validate_instrument_levels` and treats one derived `support` for threshold checks
- Need `supports: list[Decimal]` / `resistances: list[Decimal]` (API serializes as decimal strings). Empty list = unset side.

### `db.py`

- `INSTRUMENT_COLUMNS` still: `support, resistance, high_water, fixed_drawdown, ...`
- `migrate_sqlite_schema` treats `support` / `resistance` as nullable numeric columns and rebuilds the table when they are NOT NULL
- `_rebuild_sqlite_instrument_table` CREATE still has `support NUMERIC(24, 10)`, `resistance NUMERIC(24, 10)`
- Tests want: drop scalar columns; add JSON text `supports` / `resistances`; migrate `90000.1` / `110000.25` → JSON string arrays of decimal strings; ORM load of legacy DB yields `instruments[0].supports == [Decimal("90000.1")]`

### `api.py`

- `create_instrument` / `update_instrument` assign `support=payload.support`, `resistance=payload.resistance`
- `instrument_response` returns scalars
- `instrument_rule_fields_changed` compares scalar support/resistance
- After model change, compare arrays; creating/updating must persist full ladders

### `rule_persistence.py`

- `evaluate_and_persist_rules` (~55–62) still:

```python
evaluation = evaluate_rules(
    price=price,
    support=instrument.support,
    resistance=instrument.resistance,
    ...
)
```

- Required: `support, resistance = nearest_pair(instrument.supports, instrument.resistances, price)` then pass those scalars into `evaluate_rules`
- `AlertEvent` rows stay scalar. Test lock: levels `["90","98"]` / `["130","150"]`, price `100` → stored event support `98`, resistance `130`, kind `NEAR_SUPPORT`

### Leave scalar (intentionally)

- `rules.py` / `evaluate_rules` — scalar pair in, alerts out
- `rule_types.py`, `notifier.py` — alert text uses the snapshot pair
- `AlertEvent` columns
- `levels_for_alerts(support=..., resistance=..., price=...)`
- `app.py` routes — they only depend on schema/api types

---

## 8. Frontend scalar sites

All still scalar. Update after API contract + Zod boundary, per `frontend/DESIGN.md` and `AGENTS.md` (Zod on every API payload; no new CSS framework; keep a11y).

| File | What is scalar |
| --- | --- |
| `frontend/src/api/schemas.ts` | `InstrumentSchema.support` / `.resistance` via `optionalLevelString`; `CreateInstrumentRequest` `support: string; resistance: string`; `serializeInstrumentLevelsForApi` trims empty → `null` |
| `frontend/src/pages/instruments/InstrumentForm.tsx` | form fields for one support / one resistance |
| `frontend/src/pages/instruments/InstrumentList.tsx` | displays scalar levels |
| `frontend/src/pages/dashboard/PriceMonitorPanel.tsx` | uses instrument/latest-price support/resistance |
| `frontend/src/utils/instrumentMetrics.ts` | metrics from scalar pair |
| `frontend/src/utils/validation.ts` | client-side pair validation |
| `frontend/src/utils/format.ts` | level formatting |
| `frontend/src/tests/Instruments.test.tsx` | create/edit with scalar strings |
| `frontend/src/utils/instrumentMetrics.test.ts` | scalar fixtures |

`LatestPriceSchema.support_breached` / `resistance_broken` are **flags**, not levels — keep them. They remain sticky per source within the current edit cycle.

UI implication (not implemented): form must accept multiple levels (repeatable inputs or a list editor), send `supports: string[]` / `resistances: string[]`, and treat `[]` as unset. Dashboard can keep showing the nearest pair or the full ladder; decide when implementing, but Zod must match the API.

---

## 9. Tests already written (uncommitted)

These are the acceptance locks. Production must be made to pass them; do not weaken them.

### `test_support_resistance.py`

- `test_nearest_pair_picks_greatest_support_below_price_and_least_resistance_above`
- `test_nearest_pair_ignores_levels_on_the_wrong_side_of_price`
- `test_nearest_pair_returns_none_when_no_level_is_on_the_correct_side`
- `test_validate_instrument_levels_accepts_multiple_static_levels`
- `test_validate_instrument_levels_rejects_static_support_not_below_resistance` (`90,115` vs `110,120`)
- `test_validate_instrument_levels_rejects_multiple_fixed_drawdown_resistances`
- Existing static/drawdown tests updated to sequence kwargs

### `test_models.py`

- `test_instrument_accepts_multiple_supports_and_resistances` (`["140","150"]` / `["200","220"]`)
- `test_instrument_rejects_multiple_resistances_in_fixed_drawdown_mode`
- Drawdown derive/reject tests now use `supports` / `resistances`

### `test_api_instruments.py`

- `VALID_PAYLOAD` uses `supports` / `resistances` arrays
- Unset side is `[]` not `null`
- `test_create_update_list_instrument_with_multiple_supports_and_resistances`: create 3+3 levels, list, update to 2+1; decimal-string round-trip with 10 fractional digits
- Overlap case `["90","110"]` vs `["105","130"]` still 422 `"support must be less"`
- Drawdown create still derives one support into `supports: ["90000.1000000000"]`

### `test_db_migrations.py`

- Legacy numeric `support` / `resistance` → JSON `supports` / `resistances`
- After migrate: `"support" not in columns`, `"resistance" not in columns`
- Helper `json_decimals` parses JSON list of decimal strings
- ORM load of legacy static row: `.supports == [Decimal("90000.1")]`

### `test_rule_persistence.py`

- `test_evaluate_and_persist_uses_nearest_support_and_resistance_pair`
- Fixture instrument `supports=["90","98"]`, `resistances=["130","150"]`, price `100`
- Assert `NEAR_SUPPORT` and stored `AlertEvent.support == Decimal("98.0000000000")`, `.resistance == Decimal("130.0000000000")`

Frontend tests are **not** updated. They will fail once the API drops scalar fields.

---

## 10. Implementation order (next session)

Wire JSON arrays **through the stack**; keep `evaluate_rules` scalar on the selected pair.

1. **Model** — replace `Instrument.support` / `.resistance` with JSON list columns `supports` / `resistances`; coerce list items to `Decimal`; call `validate_instrument_levels(supports=..., resistances=...)`; derive drawdown into `supports = [derived]`; keep `AlertEvent` scalar.
2. **Schema** — `InstrumentRequest` / `InstrumentResponse` arrays; fix `validate_rule_contract` (threshold rules on “is there at least one support / resistance”, and derived support for drawdown without accepting client supports).
3. **API** — `api.py` create/update/response + `instrument_rule_fields_changed` compare arrays.
4. **SQLite migration** — `INSTRUMENT_COLUMNS`, `_rebuild_sqlite_instrument_table`, `migrate_sqlite_schema`: convert existing scalar values to JSON arrays (`NULL` → `[]`); rebuild so old column names disappear. Preserve other migrations (alert_mode, high_water, rule_cycle, source-mapping uniqueness).
5. **Persistence** — in `evaluate_and_persist_rules`, `nearest_pair(...)` then `evaluate_rules(support=..., resistance=...)`.
6. **Contract** — `backend/API_CONTRACT.md`: `supports` / `resistances` arrays; empty `[]` allowed on one side; static overlap rule; drawdown at most one resistance; client must not send supports in drawdown mode.
7. **Frontend** — Zod arrays, form list UX, list/dashboard display, tests. Follow `frontend/DESIGN.md`.
8. **Verify** — `pytest`, `ruff check backend/src backend/tests`, `(cd frontend && npm test && npm run build)`.

Suggested model column type: SQLAlchemy/SQLite JSON (text) storing a JSON array of decimal **strings** (matches `json_decimals` and API 10-digit strings). Do not store floats.

`create_instrument` for `fixed_drawdown`: request has no supports (or empty); after validate, model derives `supports = [derived_support(high_water, fixed_drawdown)]` the same way `_derive_fixed_drawdown_support` does today.

---

## 11. Constraints / out of scope

- Freeze-only was this session: **do not start the wiring above unless a later user message explicitly asks to implement.**
- Do not commit unless asked. Do not commit `uv.lock`.
- Do not expose secrets in code, logs, API, or commits.
- Do not change `evaluate_rules` to take arrays.
- Do not array-ify `AlertEvent` or latest-price breach flags.
- Do not add a CSS framework. Keep Zod at the API boundary.
- User-facing docs in Chinese; code comments and `API_CONTRACT.md` in English.
- Backend behavior change needs regression tests (already written — make them pass, don’t rewrite them away).
- `AGENTS.md` is the working guide; `.omo/plans/` is trace only (and may be absent).
- Type-safety: no `as any` / `@ts-ignore`. No empty `except`. Don’t delete failing tests to go green.

Risk if someone runs tests now: they fail against unmigrated `Instrument` / schemas / db. That is the freeze state, not a new bug.

---

## 12. How to resume

1. Read this file. Confirm `git log -1` is still `29d0db8` or note any new commits on top.
2. Confirm uncommitted set is still the six files in §2 (plus any work you add).
3. Re-read `support_resistance.py` (`nearest_pair` + sequence `validate_instrument_levels`) — that contract is locked.
4. Implement §10 in order. After the model change, `_assert_rule_contract` must use sequence kwargs or the process cannot even construct an `Instrument`.
5. Keep a failing test red until the matching layer is green (`test_models` after step 1, `test_db_migrations` after step 4, `test_rule_persistence` after step 5, `test_api_instruments` after steps 2–3, frontend after step 7).
6. Stop when pytest + ruff + frontend test/build pass and `API_CONTRACT.md` matches the arrays.

If HEAD moved or the six-file diff was committed/reverted, reconcile this handoff with `git status` / `git diff` before editing.
