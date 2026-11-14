PROPOSAL: needs all four teammates to agree before merge

# contracts/ and config/

`contracts/` holds the message types from `SPEC.md` section 5. `config/` holds the thresholds from `SPEC.md` section 9. Both copy the spec word for word, and `tests/test_contracts.py` reads `SPEC.md` to check that they still match.

## How to import

```python
from contracts import NameRequest, NameResult, TouchEvent, Box
from config import NAME_TIMEOUT_SECONDS, NAME_MAX_CHARS
```

`from contracts.messages import ...` and `from config.thresholds import ...` also work.

## The rule

Nobody redefines a message or a threshold locally: no copied dataclasses, no `_pending.py` shims and no literal numbers that duplicate one in `config/`. Two copies of the same class do not match on the bus, so a message would silently miss its subscriber. To change anything here, all four teammates must agree first, and the change goes in `DEVLOG.md` (`AGENTS.md` rules 1, 2 and 6).

## How this differs from the version on `main` now

`main` already has a `contracts/` and `config/` from Person 2 (commit `ae144f5`), also pending review. The thresholds are identical. The messages differ in four ways:

| | On `main` | In this proposal |
|---|---|---|
| `Box` | frozen dataclass with `.x1 .y1 .x2 .y2` | `tuple[float, float, float, float]` in `x1, y1, x2, y2` order |
| Fixed sets (`side`, `state`, `kind`, `type`, `source`, `priority`) | `str` | `Literal[...]` with the spec's values |
| `objects`, `hands`, `neighbours` | required | default to an empty list |
| Dataclasses | `frozen=True` | not frozen |

If the tuple `Box` is adopted, `scene/` and `fakes/scene/` need to change `box.x1` to `box[0]` (or `x1, y1, x2, y2 = box`), and change `Box(a, b, c, d)` to `(a, b, c, d)`. That is Person 2's call.

## Open questions

1. **Box shape.** Tuple, as proposed here, or the dataclass now on `main`? Everyone has to use the same one.
2. **Bus API.** We assume `bus.publish(msg)` and `bus.subscribe(MessageType, handler)`, owned by Person 1 in `app/`. Person 1, please confirm or correct this.
3. **Storage values not in section 9.** `storage/` uses a 3 s database connect timeout, a 1000-event write queue and a 10 s reconnect interval. Should they move to `config/`?
