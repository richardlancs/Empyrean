# contracts/ and config/

`contracts/` holds the message types from `SPEC.md` section 5. `config/` holds the thresholds from `SPEC.md` section 9. Both copy the spec word for word, and `tests/test_contracts.py` reads `SPEC.md` to check that they still match.

This is the version on `main`, in use by every module since PR #2 (2026-11-14).

## How to import

```python
from contracts import NameRequest, NameResult, TouchEvent, Box
from config import NAME_TIMEOUT_SECONDS, NAME_MAX_CHARS
```

`from contracts.messages import ...` and `from config.thresholds import ...` also work.

## The rule

Nobody redefines a message or a threshold locally: no copied dataclasses, no `_pending.py` shims and no literal numbers that duplicate one in `config/`. Two copies of the same class do not match on the bus, so a message would silently miss its subscriber. To change anything here, all four teammates must agree first, and the change goes in `DEVLOG.md` (`AGENTS.md` rules 1, 2 and 6).

## Shapes to know

| Thing | Shape |
|---|---|
| `Box` | `tuple[float, float, float, float]` in `x1, y1, x2, y2` order. Build it as `(x1, y1, x2, y2)`; `Box` is only a type hint |
| `Point` | `tuple[float, float]` in `x, y` order |
| Fixed sets (`side`, `state`, `kind`, `type`, `source`, `priority`) | `Literal[...]` with the spec's values |
| `objects`, `hands`, `neighbours` | Default to an empty list |
| Dataclasses | Not frozen |

## Bus

`app/bus.py` provides `bus.publish(msg)` and `bus.subscribe(MessageType, handler)`, keyed on the exact `contracts` class. `publish` is safe from any thread. Each subscriber has its own worker thread, and a `FrameResult` subscriber only ever gets the newest frame.

## Open question

**Storage values not in section 9.** `storage/` uses a 3 s database connect timeout, a 1000-event write queue and a 10 s reconnect interval as its own constants. Should they move to `config/`?
