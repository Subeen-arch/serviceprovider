"""Recommendation scoring: formulas, modes, edge cases, safety."""
import sys, math
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from algorithms.recommendation import (
    MODES, DEFAULT_MODE, NEUTRAL_RATING, resolve_mode, build_context,
    distance_score, rating_score, price_score, experience_score,
    calculate_recommendation_score, rank_providers,
)

PASS, FAIL = [], []
def check(n, c, d=""):
    (PASS if c else FAIL).append(n)
    print(("  PASS  " if c else "  FAIL  ") + n + (f"   [{d}]" if d and not c else ""))

def P(pid, km, rating, reviews, rate, years, **kw):
    return dict(id=pid, distance_km=km, avg_rating=rating, review_count=reviews,
                hourly_rate=rate, experience_years=years,
                business_name=f"P{pid}", **kw)

print("\n########## 49. WEIGHTS ##########")
for key, m in MODES.items():
    total = sum(m["weights"].values())
    check(f"{key} weights total 100", total == 100, str(total))
    check(f"{key} still considers all four factors",
          all(v > 0 for v in m["weights"].values()), str(m["weights"]))
w = MODES["best_overall"]["weights"]
check("best_overall = 30/30/25/15",
      (w["distance"], w["rating"], w["price"], w["experience"]) == (30, 30, 25, 15), str(w))
check("default mode is best_overall", DEFAULT_MODE == "best_overall")
check("five modes offered", len(MODES) == 5, str(list(MODES)))
for legacy, expected in [("recommended","best_overall"),("distance","closest"),
                         ("price","lowest_price"),("rating","highest_rated")]:
    check(f"legacy ?sort={legacy} still maps to {expected}", resolve_mode(legacy) == expected)
check("unknown mode falls back safely", resolve_mode("nonsense") == DEFAULT_MODE)
check("None mode falls back safely", resolve_mode(None) == DEFAULT_MODE)

print("\n########## 50. DISTANCE IS SMOOTH, NOT A CLIFF ##########")
check("0 km scores 1.00", abs(distance_score(0) - 1.0) < 1e-9)
check("5 km scores 0.50", abs(distance_score(5) - 0.5) < 1e-9)
check("10 km scores 0.33", abs(distance_score(10) - 1/3) < 1e-9)
check("monotonically decreasing",
      all(distance_score(a) > distance_score(a+0.5) for a in [0,1,2,5,10,20]))
d2, d3 = distance_score(2), distance_score(3)
check("2 km vs 3 km differ by under 8 points at weight 30",
      abs(d2-d3)*30 < 8, f"{abs(d2-d3)*30:.2f} pts")
check("farthest provider is NOT forced to zero", distance_score(50) > 0)
check("negative distance treated as 0 km", distance_score(-5) == 1.0)

print("\n########## 51. RATING IS CONFIDENCE-ADJUSTED ##########")
one_five  = rating_score(5.0, 1, prior_mean=4.0)
many_four8 = rating_score(4.8, 100, prior_mean=4.0)
check("4.8 from 100 reviews beats 5.0 from 1 review", many_four8 > one_five,
      f"4.8x100={many_four8:.4f} vs 5.0x1={one_five:.4f}")
check("5.0 from 1 review is pulled toward the prior", one_five < rating_score(5.0, 100, 4.0))
new_p = rating_score(0, 0, prior_mean=4.0)
check("no reviews lands exactly on the prior", abs(new_p - (4.0-1)/4) < 1e-9, str(new_p))
check("no reviews is NOT zero", new_p > 0)
check("no reviews beats a genuinely bad rating", new_p > rating_score(2.0, 50, 4.0))
check("more reviews at the same stars scores higher",
      rating_score(4.5, 100, 4.0) > rating_score(4.5, 2, 4.0))
check("score stays within 0..1",
      all(0 <= rating_score(r, c, 3.5) <= 1
          for r in [0,1,3,5,9,-2] for c in [0,1,10,1000,-5]))

print("\n########## 52. PRICE ##########")
check("cheapest scores 1.00", price_score(500, 500) == 1.0)
check("double the cheapest scores 0.50", abs(price_score(1000, 500) - 0.5) < 1e-9)
check("most expensive is NOT automatically zero", price_score(5000, 500) > 0)
check("identical prices all score 1.00",
      price_score(800, 800) == 1.0 and price_score(800, 800) == price_score(800, 800))
check("zero price treated as best", price_score(0, 500) == 1.0)
check("negative price treated as best", price_score(-100, 500) == 1.0)
check("no cheapest reference does not penalise", price_score(900, 0) == 1.0)
check("over budget scores 0", price_score(1200, 500, budget=1000) == 0.0)
check("within budget is unaffected", price_score(900, 500, budget=1000) > 0)
check("no budget never forces 0", price_score(99999, 500, budget=None) > 0)
check("budget of 0 means 'no budget'", price_score(99999, 500, budget=0) > 0)

print("\n########## 53. EXPERIENCE HAS DIMINISHING RETURNS ##########")
check("0 years scores 0", experience_score(0) == 0.0)
check("5 years scores 0.50", abs(experience_score(5) - 0.5) < 1e-9)
check("10 years scores 0.67", abs(experience_score(10) - 2/3) < 1e-9)
check("never reaches 1", experience_score(10000) < 1.0)
gain_0_5  = experience_score(5) - experience_score(0)
gain_20_25 = experience_score(25) - experience_score(20)
check("later years add less than early ones", gain_20_25 < gain_0_5,
      f"{gain_20_25:.4f} vs {gain_0_5:.4f}")
check("capped at 15 points under best_overall",
      experience_score(10**6) * MODES["best_overall"]["weights"]["experience"] <= 15)
check("missing experience treated as 0", experience_score(None) == 0.0)

print("\n########## 54. NO NaN / INF / OUT-OF-RANGE ##########")
nasty = [P(1, float("nan"), float("inf"), -5, float("-inf"), float("nan")),
         P(2, None, None, None, None, None),
         P(3, "abc", "xyz", "?", "", "  "),
         P(4, 0, 0, 0, 0, 0)]
ranked = rank_providers([p for p in nasty if p["distance_km"] is not None], "best_overall")
for p in ranked:
    s = p["score_exact"]
    check(f"P{p['id']} score is a finite number", isinstance(s, float) and math.isfinite(s), str(s))
    check(f"P{p['id']} score within 0..100", 0 <= s <= 100, str(s))
    for row in p["score_breakdown"]:
        check(f"P{p['id']} {row['factor']} points within range",
              0 <= row["points"] <= row["max_points"],
              f"{row['points']}/{row['max_points']}")

print("\n########## 55. EDGE CASES ##########")
check("no providers -> empty list", rank_providers([], "best_overall") == [])
check("None list -> empty list", rank_providers(None or [], "best_overall") == [])
one = rank_providers([P(1, 3, 4.5, 10, 800, 5)], "best_overall")
check("one provider still ranks", len(one) == 1)
check("one provider is the best match", one[0]["is_best_match"])
check("one provider does NOT auto-score 100", one[0]["score_exact"] < 100,
      str(one[0]["score_exact"]))
check("no route -> excluded from ranking",
      rank_providers([dict(P(1, None, 4, 5, 800, 3))], "best_overall") == [])

same = rank_providers([P(1, 3, 4.5, 10, 800, 5), P(2, 3, 4.5, 10, 800, 5)], "best_overall")
check("identical providers get identical scores",
      same[0]["score_exact"] == same[1]["score_exact"])
check("identical scores still give exactly one best match",
      sum(1 for p in same if p["is_best_match"]) == 1)
check("tie order is deterministic",
      [p["id"] for p in same] ==
      [p["id"] for p in rank_providers([P(1,3,4.5,10,800,5), P(2,3,4.5,10,800,5)], "best_overall")])

ident_price = rank_providers([P(1,2,4,5,700,3), P(2,6,4,5,700,3)], "best_overall")
check("identical prices -> equal price points",
      ident_price[0]["score_breakdown"][2]["points"] == ident_price[1]["score_breakdown"][2]["points"])
ident_dist = rank_providers([P(1,4,4,5,600,3), P(2,4,4,5,900,3)], "best_overall")
check("identical distances -> equal distance points",
      ident_dist[0]["score_breakdown"][0]["points"] == ident_dist[1]["score_breakdown"][0]["points"])

print("\n########## 56. NEW PROVIDERS ARE NOT DUMPED AT THE BOTTOM ##########")
listing = [P(1, 2.0, 0,   0,  700, 2),      # new, near, cheap
           P(2, 9.0, 4.9, 60, 1500, 12)]    # established but far and pricey
r = rank_providers(listing, "best_overall")
check("new provider flagged", [p for p in r if p["id"] == 1][0]["is_new"])
check("established provider not flagged", not [p for p in r if p["id"] == 2][0]["is_new"])
check("a good new provider can outrank an established one", r[0]["id"] == 1,
      f"order={[p['id'] for p in r]}")
r2 = rank_providers([P(1, 8, 0, 0, 2000, 0), P(2, 2, 4.6, 40, 700, 8)], "best_overall")
check("but a weak new provider does not win", r2[0]["id"] == 2)

print("\n########## 57. MODES RE-RANK ##########")
pool = [P(1, 1.0, 3.6, 8,  1500, 1),    # closest, dear, weak rating
        P(2, 9.0, 4.9, 80, 900,  3),    # far, best rated
        P(3, 6.0, 4.0, 10, 400,  2),    # cheapest
        P(4, 7.0, 4.1, 12, 1000, 25)]   # most experienced
wins = {}
for key in MODES:
    order = [p["id"] for p in rank_providers([dict(x) for x in pool], key)]
    wins[key] = order[0]
    print(f"        {key:17} -> {order}")
check("Closest picks the nearest", wins["closest"] == 1, str(wins))
check("Lowest price picks the cheapest", wins["lowest_price"] == 3, str(wins))
check("Highest rated picks the best rated", wins["highest_rated"] == 2, str(wins))
check("Most experienced picks the veteran", wins["most_experienced"] == 4, str(wins))
check("changing mode changes the ranking", len(set(wins.values())) > 1, str(wins))

print("\n########## 58. SORTING + DISPLAY PRECISION ##########")
r = rank_providers([dict(x) for x in pool], "best_overall")
check("sorted high to low", all(r[i]["score_exact"] >= r[i+1]["score_exact"] for i in range(len(r)-1)))
check("exactly one best match", sum(1 for p in r if p["is_best_match"]) == 1)
check("best match is the top scorer", r[0]["is_best_match"])
check("displayed score rounded to 1dp",
      all(round(p["recommendation_score"], 1) == p["recommendation_score"] for p in r))
check("full precision kept for sorting",
      any(p["score_exact"] != p["recommendation_score"] for p in r))

print("\n########## 59. BREAKDOWN MATCHES THE SCORE ##########")
for p in r:
    total = sum(row["points"] for row in p["score_breakdown"])
    check(f"P{p['id']} breakdown adds up to the score",
          abs(total - p["recommendation_score"]) <= 0.2,
          f"rows={total:.2f} score={p['recommendation_score']}")
    check(f"P{p['id']} shows all four factors",
          [row["factor"] for row in p["score_breakdown"]] ==
          ["Distance", "Rating", "Price", "Experience"])
ctx = build_context(pool)
solo = calculate_recommendation_score(pool[0], "best_overall", ctx)
check("calculate_recommendation_score matches rank_providers",
      abs(solo["score"] - [p for p in r if p["id"] == 1][0]["score_exact"]) < 1e-9)
check("calculate_recommendation_score works with no context",
      0 <= calculate_recommendation_score(pool[0])["score"] <= 100)

print("\n########## 60. DETERMINISM ##########")
runs = [[(p["id"], p["score_exact"]) for p in rank_providers([dict(x) for x in pool], "best_overall")]
        for _ in range(5)]
check("same input gives the same output every time", all(x == runs[0] for x in runs))

print(f"\n===== recommendation: {len(PASS)} passed, {len(FAIL)} failed =====")
if FAIL:
    print("FAILURES:"); [print("   -", f) for f in FAIL]
