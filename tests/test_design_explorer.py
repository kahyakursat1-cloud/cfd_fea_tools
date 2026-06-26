import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import design_explorer as de  # noqa: E402


def test_lhs_coverage():
    s = de.lhs_sample({"x": (0.0, 10.0), "y": (1.0, 2.0)}, 20, seed=1)
    assert len(s) == 20
    assert all(0 <= p["x"] <= 10 and 1 <= p["y"] <= 2 for p in s)
    xs = sorted(p["x"] for p in s)            # LHS → her dilimde bir örnek (boşluk yok)
    assert xs[0] < 1.0 and xs[-1] > 9.0       # uçlar dolu


def _quad(params):                            # analitik mock: cd min @ x=3
    x = params["x"]
    return de.DesignPoint(params, {"cd": (x - 3.0) ** 2 + 0.1}, source="mock")


def test_explore_finds_minimum():
    res = de.explore({"x": (0.0, 6.0)}, _quad, n=40, objectives=["cd"])
    assert res["n_gecerli"] == 40
    assert abs(res["en_iyi"]["params"]["x"] - 3.0) < 0.5     # min'e yakın
    assert res["en_iyi"]["objectives"]["cd"] < 0.4


def test_pareto_front_tradeoff():
    # iki amaç çelişir: f1=x, f2=1-x → tüm iç noktalar Pareto-optimal
    pts = [de.DesignPoint({"x": x}, {"f1": x, "f2": 1 - x}) for x in (0.0, 0.25, 0.5, 0.75, 1.0)]
    front = de.pareto_front(pts, ["f1", "f2"])
    assert len(front) == 5                    # hiçbiri diğerini domine etmez


def test_pareto_dominated_removed():
    pts = [de.DesignPoint({"i": 0}, {"f1": 1.0, "f2": 1.0}),   # domine eden
           de.DesignPoint({"i": 1}, {"f1": 2.0, "f2": 2.0})]   # domine edilen
    front = de.pareto_front(pts, ["f1", "f2"])
    assert len(front) == 1 and front[0].params["i"] == 0


def test_invalid_points_excluded():
    def evalfn(p):
        return de.DesignPoint(p, {} if p["x"] > 5 else {"cd": p["x"]}, gecerli=p["x"] <= 5)
    res = de.explore({"x": (0.0, 10.0)}, evalfn, n=30, objectives=["cd"])
    assert res["n_gecerli"] < 30 and res["en_iyi"]["objectives"]["cd"] >= 0
