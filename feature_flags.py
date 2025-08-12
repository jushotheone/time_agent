# feature_flags.py
from __future__ import annotations
import os, json, threading, time
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Callable, Dict, Optional

# ---------- Defaults: full 18 workflows + #0 subfeatures ----------
DEFAULT_FLAGS: Dict[str, bool] = {
    # WF0 – Live Session Stewardship (sub-flags for granular rollout)
    "WF0_ADAPTIVE": True,          # enable the whole-day FSM loop
    "WF0_FTM": True,               # Free Time Mode
    "WF0_DS_MODE": False,          # Drill Sergeant tone enabled
    "WF0_SNOOZE": True,            # SNOOZED state + buttons
    "WF0_INTERRUPTED": True,       # INTERRUPTED state (calls/driving)
    "WF0_RESET_DAY": True,         # Reset My Day routine
    "WF0_MINIMAL_PLAN": True,      # Morning/early Minimal Plan
    "WF0_RIGIDITY": True,          # hard/firm/soft/free rescheduling rules
    "WF0_BUFFERS": True,           # 5–10m transition + travel buffers
    "WF0_JETLAG": True,            # soften tones on tz shift
    "WF0_SIGNALS": False,          # opt-in device/activity signals

    # WF1–WF17
    "WF1_REMINDERS": True,
    "WF2_CONVERSATION": True,
    "WF3_QUADRANTS": False,
    "WF4_EVENING_REVIEW": True,
    "WF5_ACCOUNTABILITY": False,
    "WF6_SELF_CORRECT": False,
    "WF7_FAITH_INTEGRATION": False,
    "WF8_MICRO_COACH": False,
    "WF9_MEMORY": True,
    "WF10_GOALS": False,
    "WF11_PEOPLE_PLACES": False,
    "WF12_THEMES": False,
    "WF13_WEEKLY_PLANNING": False,
    "WF14_CASUAL_CAPTURE": False,
    "WF15_VOICE_UI": False,
    "WF16_TIME_AUDIT": False,
    "WF17_CONTENT_AWARE": False,
}

# Optional file for overrides (hot‑reloadable).
FLAGS_FILE = os.getenv("FLAGS_FILE", "config/flags.yml")  # supports .yml or .json

# ---------- Types ----------
@dataclass
class FlagRollout:
    # percentage rollout (0-100), optional time window (epoch seconds)
    percent: int = 100
    start_ts: Optional[int] = None
    end_ts: Optional[int] = None

@dataclass
class FlagStore:
    values: Dict[str, bool] = field(default_factory=lambda: DEFAULT_FLAGS.copy())
    user_overrides: Dict[str, Dict[str, bool]] = field(default_factory=dict)
    rollouts: Dict[str, FlagRollout] = field(default_factory=dict)
    _mtime: float = 0.0

# ---------- Helper: YAML/JSON loader (no external deps) ----------
def _load_config_file(path: Path) -> Dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    # Prefer PyYAML if installed (handles {}, [], numbers, etc.)
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass

    # Fallback: current minimal parser
    data: Dict = {}
    stack = [data]
    indents = [0]
    last_key = None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        key, _, raw = line.strip().partition(":")
        val = raw.strip()

        # handle explicit empty map/list literals
        if val in ("{}", "[]"):
            parsed = {} if val == "{}" else []
        elif val.lower() in ("true","yes","on"):
            parsed = True
        elif val.lower() in ("false","no","off"):
            parsed = False
        elif val.isdigit():
            parsed = int(val)
        else:
            parsed = val  # string

        while indent < indents[-1]:
            stack.pop(); indents.pop()

        if indent > indents[-1]:
            if last_key is None:
                # malformed indent; treat as top-level
                indent = indents[-1]
            else:
                parent = stack[-1]
                if not isinstance(parent.get(last_key), dict):
                    parent[last_key] = {}
                stack.append(parent[last_key]); indents.append(indent)

        stack[-1][key] = parsed
        last_key = key
    return data

# ---------- Core Flags manager ----------
# ---------- Core Flags manager ----------
class Flags:
    def __init__(self):
        self._lock = threading.RLock()
        self._store = FlagStore()
        self.reload()  # env/file overrides at boot

    # public API
    def get(self, key: str, default: bool = False, user_id: Optional[str]=None) -> bool:
        with self._lock:
            if user_id and key in self._store.user_overrides.get(str(user_id), {}):
                return self._store.user_overrides[str(user_id)][key]
            base = self._store.values.get(key, default)
            if key in self._store.rollouts:
                if not self._rollout_allows(user_id, self._store.rollouts[key]):
                    return False
            return base

    def set(self, key: str, value: bool, user_id: Optional[str]=None):
        with self._lock:
            if user_id:
                self._store.user_overrides.setdefault(str(user_id), {})[key] = value
            else:
                self._store.values[key] = value

    def set_rollout(self, key: str, percent: int, start_ts: Optional[int]=None, end_ts: Optional[int]=None):
        with self._lock:
            self._store.rollouts[key] = FlagRollout(percent=percent, start_ts=start_ts, end_ts=end_ts)

    def bulk(self) -> Dict[str, bool]:
        with self._lock:
            return self._store.values.copy()

    def reload(self):
        with self._lock:
            store = FlagStore(values=DEFAULT_FLAGS.copy())

            # env overrides
            for k in list(store.values.keys()):
                envv = os.getenv(f"FLAG_{k}")
                if envv is not None:
                    store.values[k] = envv.lower() in ("1","true","yes","on")

            # file overrides
            path = Path(FLAGS_FILE)
            cfg = _load_config_file(path)
            cfg = cfg if isinstance(cfg, dict) else {}

            flags_map = cfg.get("flags") or {}
            user_overrides = cfg.get("user_overrides") or {}
            rollouts = cfg.get("rollouts") or {}

            if not isinstance(flags_map, dict): flags_map = {}
            if not isinstance(user_overrides, dict): user_overrides = {}
            if not isinstance(rollouts, dict): rollouts = {}

            for k, v in flags_map.items():
                if isinstance(v, bool):
                    store.values[k] = v

            for uid, flags in user_overrides.items():
                if isinstance(flags, dict):
                    store.user_overrides[str(uid)] = {k: bool(v) for k, v in flags.items()}

            for k, r in rollouts.items():
                if isinstance(r, dict):
                    store.rollouts[k] = FlagRollout(
                        percent=int(r.get("percent", 100)),
                        start_ts=r.get("start_ts"),
                        end_ts=r.get("end_ts")
                    )

            self._store = store
            self._store._mtime = path.stat().st_mtime if path.exists() else time.time()

    def maybe_hot_reload(self):
        path = Path(FLAGS_FILE)
        if not path.exists():
            return
        try:
            mtime = path.stat().st_mtime
            if mtime > self._store._mtime:
                self.reload()
        except Exception:
            pass

    def if_flag(self, flag_name: str):
        def deco(fn: Callable):
            @wraps(fn)
            def wrapper(*args, **kwargs):
                user_id = kwargs.get("user_id") or kwargs.get("uid")
                if self.get(flag_name, default=False, user_id=user_id):
                    return fn(*args, **kwargs)
                return None
            return wrapper
        return deco

    def temp(self, overrides: Dict[str, bool]):
        class _Ctx:
            def __init__(_self, outer: Flags, ov: Dict[str, bool]):
                _self.outer = outer; _self.ov = ov; _self.prev = None
            def __enter__(_self):
                with _self.outer._lock:
                    _self.prev = _self.outer._store.values.copy()
                    _self.outer._store.values.update(_self.ov)
            def __exit__(_self, exc_type, exc, tb):
                with _self.outer._lock:
                    _self.outer._store.values = _self.prev
        return _Ctx(self, overrides)

    def _rollout_allows(self, user_id: Optional[str], r: FlagRollout) -> bool:
        now = int(time.time())
        if r.start_ts and now < r.start_ts: return False
        if r.end_ts and now > r.end_ts: return False
        if r.percent >= 100: return True
        if r.percent <= 0: return False
        bucket_source = str(user_id or "0")
        bucket = (sum(ord(c) for c in bucket_source) % 100)
        return bucket < r.percent


# Singleton
FLAGS = Flags()

# Convenience helpers / back-compat
def enabled(name: str, user_id: Optional[str] = None) -> bool:
    return FLAGS.get(name, False, user_id)

def ff_is_enabled(name: str, user_id: Optional[str] = None) -> bool:
    return FLAGS.get(name, False, user_id)

# so `from feature_flags import ff` continues to work
ff = FLAGS