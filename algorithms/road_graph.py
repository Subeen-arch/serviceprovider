"""The road network that Dijkstra runs on.

This is a simplified but real map of the Kathmandu valley: every NODE is an
actual junction or landmark with its true coordinates, and every EDGE is a road
that really connects those two junctions.

It is deliberately small (about 45 junctions) so the graph can be drawn on paper
and the algorithm's behaviour can be checked by hand during a viva. Edge weights
are not typed in by hand - they are computed from the real coordinates, so the
weights stay correct and honest.
"""

# junction id -> (display name, latitude, longitude)
NODES = {
    # --- city core ---
    "ratnapark":      ("Ratna Park",          27.7047, 85.3140),
    "newroad":        ("New Road",            27.7025, 85.3095),
    "durbarmarg":     ("Durbar Marg",         27.7108, 85.3175),
    "thamel":         ("Thamel",              27.7154, 85.3123),
    "putalisadak":    ("Putalisadak",         27.7052, 85.3222),
    "dillibazar":     ("Dillibazar",          27.7062, 85.3292),
    "naxal":          ("Naxal",               27.7136, 85.3262),

    # --- north ---
    "lainchaur":      ("Lainchaur",           27.7196, 85.3155),
    "lazimpat":       ("Lazimpat",            27.7238, 85.3208),
    "baluwatar":      ("Baluwatar",           27.7252, 85.3292),
    "maharajgunj":    ("Maharajgunj",         27.7372, 85.3300),
    "narayangopal":   ("Narayan Gopal Chowk", 27.7392, 85.3335),
    "basundhara":     ("Basundhara",          27.7420, 85.3232),
    "budhanilkantha": ("Budhanilkantha",      27.7652, 85.3622),

    # --- north-west (ring road) ---
    "samakhusi":      ("Samakhusi",           27.7312, 85.3162),
    "gongabu":        ("Gongabu",             27.7356, 85.3122),
    "balaju":         ("Balaju",              27.7356, 85.3022),
    "swayambhu":      ("Swayambhu",           27.7146, 85.2902),
    "sitapaila":      ("Sitapaila",           27.7102, 85.2792),

    # --- west ---
    "kalanki":        ("Kalanki",             27.6936, 85.2812),
    "kalimati":       ("Kalimati",            27.6962, 85.2962),
    "teku":           ("Teku",                27.6960, 85.3062),
    "balkhu":         ("Balkhu",              27.6846, 85.2962),
    "kirtipur":       ("Kirtipur",            27.6790, 85.2792),

    # --- centre-south ---
    "tripureshwor":   ("Tripureshwor",        27.6936, 85.3142),
    "thapathali":     ("Thapathali",          27.6916, 85.3190),
    "maitighar":      ("Maitighar",           27.6936, 85.3222),
    "babarmahal":     ("Babarmahal",          27.6938, 85.3292),

    # --- Lalitpur ---
    "kupondole":      ("Kupondole",           27.6872, 85.3156),
    "sanepa":         ("Sanepa",              27.6852, 85.3082),
    "pulchowk":       ("Pulchowk",            27.6790, 85.3172),
    "jawalakhel":     ("Jawalakhel",          27.6732, 85.3122),
    "lagankhel":      ("Lagankhel",           27.6672, 85.3232),
    "satdobato":      ("Satdobato",           27.6582, 85.3252),
    "ekantakuna":     ("Ekantakuna",          27.6652, 85.3052),
    "gwarko":         ("Gwarko",              27.6672, 85.3322),
    "imadol":         ("Imadol",              27.6652, 85.3402),

    # --- east ---
    "newbaneshwor":   ("New Baneshwor",       27.6890, 85.3350),
    "oldbaneshwor":   ("Old Baneshwor",       27.6978, 85.3396),
    "gaushala":       ("Gaushala",            27.7085, 85.3440),
    "chabahil":       ("Chabahil",            27.7175, 85.3462),
    "boudha":         ("Boudha",              27.7215, 85.3620),
    "jorpati":        ("Jorpati",             27.7262, 85.3722),
    "tinkune":        ("Tinkune",             27.6822, 85.3452),
    "koteshwor":      ("Koteshwor",           27.6781, 85.3492),
    "sinamangal":     ("Sinamangal",          27.6952, 85.3540),
    "airport":        ("Tribhuvan Airport",   27.6966, 85.3591),
    "thimi":          ("Thimi",               27.6822, 85.3822),
    "bhaktapur":      ("Bhaktapur",           27.6712, 85.4290),
}

# Roads. Each pair is one two-way road between two junctions.
EDGES = [
    # city core
    ("ratnapark", "newroad"),
    ("ratnapark", "durbarmarg"),
    ("ratnapark", "putalisadak"),
    ("ratnapark", "tripureshwor"),
    ("newroad", "teku"),
    ("newroad", "tripureshwor"),
    ("durbarmarg", "thamel"),
    ("durbarmarg", "naxal"),
    ("putalisadak", "dillibazar"),
    ("putalisadak", "maitighar"),
    ("dillibazar", "naxal"),
    ("dillibazar", "gaushala"),

    # north
    ("thamel", "lainchaur"),
    ("lainchaur", "lazimpat"),
    ("lainchaur", "balaju"),
    ("lazimpat", "baluwatar"),
    ("lazimpat", "maharajgunj"),
    ("naxal", "baluwatar"),
    ("baluwatar", "maharajgunj"),
    ("maharajgunj", "narayangopal"),
    ("narayangopal", "basundhara"),
    ("narayangopal", "budhanilkantha"),
    ("narayangopal", "chabahil"),

    # ring road, north-west arc
    ("basundhara", "samakhusi"),
    ("samakhusi", "gongabu"),
    ("gongabu", "balaju"),
    ("balaju", "swayambhu"),
    ("swayambhu", "sitapaila"),
    ("swayambhu", "kalanki"),
    ("sitapaila", "kalanki"),

    # west
    ("kalanki", "kalimati"),
    ("kalanki", "balkhu"),
    ("kalimati", "teku"),
    ("kalimati", "balkhu"),
    ("balkhu", "kirtipur"),
    ("balkhu", "ekantakuna"),
    ("teku", "tripureshwor"),

    # centre-south
    ("tripureshwor", "thapathali"),
    ("thapathali", "maitighar"),
    ("thapathali", "kupondole"),
    ("maitighar", "babarmahal"),
    ("babarmahal", "newbaneshwor"),

    # Lalitpur
    ("kupondole", "sanepa"),
    ("kupondole", "pulchowk"),
    ("sanepa", "jawalakhel"),
    ("pulchowk", "jawalakhel"),
    ("pulchowk", "lagankhel"),
    ("jawalakhel", "ekantakuna"),
    ("jawalakhel", "lagankhel"),
    ("lagankhel", "satdobato"),
    ("lagankhel", "gwarko"),
    ("satdobato", "gwarko"),
    ("satdobato", "ekantakuna"),
    ("gwarko", "imadol"),
    ("gwarko", "koteshwor"),
    ("imadol", "koteshwor"),

    # east
    ("newbaneshwor", "oldbaneshwor"),
    ("newbaneshwor", "tinkune"),
    ("oldbaneshwor", "gaushala"),
    ("gaushala", "chabahil"),
    ("gaushala", "sinamangal"),
    ("chabahil", "boudha"),
    ("boudha", "jorpati"),
    ("sinamangal", "airport"),
    ("airport", "tinkune"),
    ("tinkune", "koteshwor"),
    ("koteshwor", "thimi"),
    ("thimi", "bhaktapur"),
]
