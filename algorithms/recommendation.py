"""Weighted recommendation scoring.

This is *not* machine learning and it is not a prediction. It is a transparent
weighted decision score: four measurable facts about a provider are each put on
a 0-1 scale, multiplied by a weight, and added up to give a score out of 100.

    score = distance_points + rating_points + price_points + experience_points

The weights depend on the mode the customer picked. "Best overall" is the
default:

    Distance 30 | Rating 30 | Price 25 | Experience 15

Each factor uses a *smooth* curve rather than min-max normalisation, so a
provider's score depends on its own real values, not on who else happens to be
in the list. That means a provider slightly farther away scores slightly lower
- not dramatically lower - and adding one very distant provider no longer
changes everybody else's score.

The same input always gives the same output: there is no randomness anywhere,
and no provider is ever given a hand-written score.
"""

import math

# --------------------------------------------------------------------------
# Tuning constants. These shape the curves and are explained where used.
# --------------------------------------------------------------------------

# A provider this far away scores half the distance points. 5 km is a sensible
# "a bit far but still local" figure for the Kathmandu valley.
DISTANCE_HALF_KM = 5.0

# How many reviews a provider needs before its own average is trusted more
# than the platform average. With 5, a provider with 5 reviews sits halfway
# between the two.
RATING_CONFIDENCE = 5

# Used as the rating prior when nobody in the list has any reviews at all.
NEUTRAL_RATING = 3.5

# Ratings run 1-5, so this is the range the Bayesian average is mapped from.
MIN_RATING, MAX_RATING = 1.0, 5.0

# Years of experience for half the experience points. Diminishing returns mean
# 20 years is better than 10, but not twice as good.
EXPERIENCE_HALF_YEARS = 5.0

# --------------------------------------------------------------------------
# Modes. Every mode still considers all four factors - a mode only changes how
# much each one matters. Each set of weights adds up to 100.
# --------------------------------------------------------------------------
MODES = {
    "best_overall": {
        "label": "Best overall",
        "weights": {"distance": 30, "rating": 30, "price": 25, "experience": 15},
    },
    # In the focused modes the chosen factor is worth 60 - more than the other
    # three put together - so it decides the order in all but extreme cases,
    # while the remaining 40 still keeps an awful provider from winning on one
    # strength alone.
    "closest": {
        "label": "Closest",
        "weights": {"distance": 60, "rating": 20, "price": 12, "experience": 8},
    },
    "lowest_price": {
        "label": "Lowest price",
        "weights": {"distance": 15, "rating": 17, "price": 60, "experience": 8},
    },
    "highest_rated": {
        "label": "Highest rated",
        "weights": {"distance": 15, "rating": 60, "price": 17, "experience": 8},
    },
    "most_experienced": {
        "label": "Most experienced",
        "weights": {"distance": 15, "rating": 20, "price": 10, "experience": 55},
    },
}

DEFAULT_MODE = "best_overall"

# Older links used ?sort=... so they keep working.
LEGACY_SORT_ALIASES = {
    "recommended": "best_overall",
    "distance": "closest",
    "price": "lowest_price",
    "rating": "highest_rated",
}


def resolve_mode(value):
    """Turn whatever arrived in the URL into a mode key we support."""
    if value in MODES:
        return value
    return LEGACY_SORT_ALIASES.get(value, DEFAULT_MODE)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def _number(value, default=0.0):
    """Read a database value as a float, refusing NaN and infinity."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _clamp(value, low=0.0, high=1.0):
    """Keep a factor score inside its allowed range, whatever went in."""
    if not math.isfinite(value):
        return low
    return max(low, min(high, value))


# --------------------------------------------------------------------------
# The four factor scores. Each returns a value between 0 and 1.
# --------------------------------------------------------------------------
def distance_score(distance_km):
    """Nearer is better, on a smooth curve.

        score = 1 / (1 + km / 5)

    0 km -> 1.00, 2 km -> 0.71, 5 km -> 0.50, 10 km -> 0.33.

    Because the curve is gentle, a provider 3 km away is not punished the way
    min-max normalisation would punish it just for being the farthest of three.
    """
    km = max(0.0, _number(distance_km))
    return _clamp(1.0 / (1.0 + km / DISTANCE_HALF_KM))


def rating_score(avg_rating, review_count, prior_mean=NEUTRAL_RATING):
    """Stars, weighted by how much evidence there is behind them.

    Uses a Bayesian (confidence-adjusted) average:

        adjusted = (C * prior + sum_of_stars) / (C + review_count)

    where C = 5. One 5.0-star review is pulled most of the way back towards the
    platform average; a hundred 4.8-star reviews are trusted almost completely.
    A provider with no reviews lands exactly on the prior, which is a fair
    middling score rather than zero.

    The result is mapped from the 1-5 star range onto 0-1.
    """
    count = max(0, int(_number(review_count)))
    prior = _clamp(_number(prior_mean, NEUTRAL_RATING), MIN_RATING, MAX_RATING)

    if count <= 0:
        adjusted = prior
    else:
        average = _clamp(_number(avg_rating, prior), MIN_RATING, MAX_RATING)
        adjusted = ((RATING_CONFIDENCE * prior) + (average * count)) / (
            RATING_CONFIDENCE + count
        )

    return _clamp((adjusted - MIN_RATING) / (MAX_RATING - MIN_RATING))


def price_score(hourly_rate, cheapest_rate, budget=None):
    """Cheaper is better, measured against the cheapest provider available.

        score = cheapest / this provider's rate

    The cheapest provider scores 1.00; one charging twice as much scores 0.50.
    Nobody is dropped to zero just for being the most expensive - that only
    happens when a rate is over a budget the customer actually set.

    If every provider charges the same they all score 1.00, and a rate of zero
    (or a missing rate) is treated as the best possible price.
    """
    rate = _number(hourly_rate)
    limit = _number(budget, 0.0)

    if limit > 0 and rate > limit:
        return 0.0            # outside the customer's stated budget

    if rate <= 0:
        return 1.0            # free, or no rate recorded

    cheapest = _number(cheapest_rate)
    if cheapest <= 0:
        return 1.0            # no usable comparison, so do not penalise

    return _clamp(cheapest / rate)


def experience_score(experience_years):
    """More years is better, with diminishing returns.

        score = years / (years + 5)

    0 yr -> 0.00, 5 yr -> 0.50, 10 yr -> 0.67, 20 yr -> 0.80.

    The curve never reaches 1, so a very long career cannot run away with the
    ranking - at 15% weight it is worth at most 15 points.
    """
    years = max(0.0, _number(experience_years))
    return _clamp(years / (years + EXPERIENCE_HALF_YEARS))


# --------------------------------------------------------------------------
# Scoring one provider, and ranking a list of them
# --------------------------------------------------------------------------
def build_context(providers, budget=None):
    """Work out the few facts a single provider's score needs from the list.

    Only two things depend on the other candidates: the cheapest rate on offer,
    and the average rating used as the Bayesian prior.
    """
    rated = [
        _clamp(_number(p.get("avg_rating")), MIN_RATING, MAX_RATING)
        for p in providers
        if int(_number(p.get("review_count"))) > 0
    ]
    rates = [
        _number(p.get("hourly_rate"))
        for p in providers
        if _number(p.get("hourly_rate")) > 0
    ]
    return {
        "rating_prior": sum(rated) / len(rated) if rated else NEUTRAL_RATING,
        "cheapest_rate": min(rates) if rates else 0.0,
        "budget": budget,
    }


def calculate_recommendation_score(provider, mode=DEFAULT_MODE, context=None):
    """Score one provider out of 100 and explain how.

    Returns {"score": float, "breakdown": [...]}. The breakdown holds exactly
    the numbers that made up the score, so the "How this score was calculated"
    panel can never disagree with the ranking.
    """
    mode = resolve_mode(mode)
    weights = MODES[mode]["weights"]
    if context is None:
        context = build_context([provider])

    review_count = max(0, int(_number(provider.get("review_count"))))
    distance_km = _number(provider.get("distance_km"))
    rate = _number(provider.get("hourly_rate"))
    years = max(0.0, _number(provider.get("experience_years")))
    prior = context.get("rating_prior", NEUTRAL_RATING)

    factors = {
        "distance": distance_score(distance_km),
        "rating": rating_score(provider.get("avg_rating"), review_count, prior),
        "price": price_score(rate, context.get("cheapest_rate"), context.get("budget")),
        "experience": experience_score(years),
    }

    points = {name: weights[name] * value for name, value in factors.items()}
    score = _clamp(sum(points.values()), 0.0, 100.0)

    budget = _number(context.get("budget"), 0.0)
    over_budget = budget > 0 and rate > budget

    breakdown = [
        {
            "factor": "Distance",
            "value": f"{distance_km:.2f} km away",
            "points": round(points["distance"], 1),
            "max_points": weights["distance"],
        },
        {
            "factor": "Rating",
            "value": (
                f"{_number(provider.get('avg_rating')):.1f} from "
                f"{review_count} review{'s' if review_count != 1 else ''}"
                if review_count
                else f"no reviews yet (treated as {prior:.1f})"
            ),
            "points": round(points["rating"], 1),
            "max_points": weights["rating"],
        },
        {
            "factor": "Price",
            "value": (
                f"Rs {rate:.0f} / hr" + (" - over your budget" if over_budget else "")
            ),
            "points": round(points["price"], 1),
            "max_points": weights["price"],
        },
        {
            "factor": "Experience",
            "value": f"{years:.0f} year{'s' if years != 1 else ''}",
            "points": round(points["experience"], 1),
            "max_points": weights["experience"],
        },
    ]

    return {"score": score, "breakdown": breakdown}


def rank_providers(providers, mode=DEFAULT_MODE, budget=None):
    """Score every provider and return them best first.

    Each provider gains:
        recommendation_score  - rounded to one decimal place, for display
        score_exact           - full precision, used for the sort
        score_breakdown       - the numbers behind the score
        is_new                - true when the provider has no reviews yet
        is_best_match         - true for the single highest scorer only
    """
    mode = resolve_mode(mode)

    if not providers:
        return []

    # A provider with no road route has no distance to score, so it is left out
    # here and shown separately by the caller rather than given a made-up one.
    rankable = [p for p in providers if p.get("distance_km") is not None]
    if not rankable:
        return []

    context = build_context(rankable, budget)

    for provider in rankable:
        result = calculate_recommendation_score(provider, mode, context)
        provider["score_exact"] = result["score"]
        provider["recommendation_score"] = round(result["score"], 1)
        provider["score_breakdown"] = result["breakdown"]
        provider["is_new"] = int(_number(provider.get("review_count"))) <= 0

    # Highest score first. Ties fall back to the nearer provider, then to the
    # id, so the order is always the same for the same data.
    rankable.sort(
        key=lambda p: (
            -p["score_exact"],
            _number(p.get("distance_km")),
            int(_number(p.get("id"))),
        )
    )

    for position, provider in enumerate(rankable):
        provider["is_best_match"] = position == 0

    return rankable
