"""Release-5 per-showing planted effects: each metric's two groups (n, purchases), the ratio, and the purchases needed at 80 % power
(two-sided 5 %, log rate-ratio test; at low rates Var(ln r) ~ 1/xA + 1/xB). Read-only on the data dir given."""
import json, math, sys, inspect
from pathlib import Path
sys.path.insert(0, '.')
import scripts.planted_effect_metrics as pm, scripts.state_effect_metrics as sm, scripts.review_effect_metrics as rm, scripts.acquisition_effect_metrics as am
calls = []
orig = pm._rate
def rec(rows, outcome="purchased"):
    rows = list(rows); calls.append((len(rows), sum(r[outcome] for r in rows), outcome)); return orig(rows, outcome)
for m in (pm, sm, rm, am):
    if hasattr(m, '_rate'): m._rate = rec
fx = pm.Fixtures(Path(sys.argv[1]))
imps = fx.impressions(); list_purchases = sum(r['purchased'] for r in imps)
traits = fx.traits(); lifestyles = sorted({t['lifestyle'] for t in traits.values()})
levels = sorted({t['discount_sensitivity'] for t in traits.values()})
K = (1.959964 + 0.841621) ** 2
out = []
for m in (pm, sm, rm, am):
    for name, f in inspect.getmembers(m, inspect.isfunction):
        if f.__module__ != m.__name__ or name.startswith('_') or name == 'clear_caches': continue
        params = list(inspect.signature(f).parameters)[1:]
        argsets = [()] if not params else [(a,) for a in (lifestyles if 'lifestyle' in params else levels)] if len(params) == 1 and params[0] in ('lifestyle', 'level') else None
        if argsets is None: continue
        for args in argsets:
            calls.clear()
            try: v = f(fx, *args)
            except Exception as e: continue
            pur = [c for c in calls if c[2] == 'purchased']
            if len(pur) != 2 or not isinstance(v, float) or v <= 0: continue
            (na, xa, _), (nb, xb, _) = pur
            if xa == 0 or xb == 0: continue
            r = (xa / na) / (xb / nb)
            if abs(math.log(r)) < 1e-9: continue
            q = K * (1 / xa + 1 / xb) / math.log(r) ** 2   # the share of release 5's purchases that still gives 80 % power
            out.append({'metric': f'{m.__name__.split(".")[-1]}.{name}{args if args else ""}', 'ratio': round(r, 3), 'groups': [[na, xa], [nb, xb]], 'share_needed': round(q, 3), 'list_purchases_needed': math.ceil(q * list_purchases)})
print(json.dumps({'list_impressions': len(imps), 'list_purchases': list_purchases, 'effects': sorted(out, key=lambda e: -e['share_needed'])}, indent=1))
