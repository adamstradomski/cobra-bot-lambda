"""Short ID names for table columns (embed format A-1, A-3): data only.

Keys are the text before the first `:` of a Cobra identity; values are at most 9
columns. IDs missing here fall back to a derived name (`text.corp_label`,
`text.runner_label`) and are logged, so they can be added.
"""

CORP_SHORT_NAMES: dict[str, str] = {
    # A-3 (from the sample data)
    "Nuvem SA": "Nuvem",
    "Méliès U": "Méliès",
    "Nebula Talent Management": "Nebula",
    "Haas-Bioroid": "HB",
    "AU Co.": "AU Co.",
    "Weyland Consortium": "Weyland",
    "Ob Superheavy Logistics": "Ob",
    "Editorial Division": "Editorial",
    "The Zwicky Group": "Zwicky",
    "BANGUN": "BANGUN",
    "Issuaq Adaptics": "Issuaq",
    "Earth Station": "Earth St.",
    "Synapse Global": "Synapse",
    "GameNET": "GameNET",
    # Seen in the test fixtures
    "Epiphany Analytica": "Epiphany",
    "Hyoubu Institute": "Hyoubu",
    "LEO Construction": "LEO",
    "PT Untaian": "Untaian",
    "Poétrï Luxury Brands": "Poétrï",
    "The Syndicate": "Syndicate",
    "Thule Subsea": "Thule",
}

RUNNER_SHORT_NAMES: dict[str, str] = {
    # A-3 (from the sample data)
    "Arissana Rocha Nahu": "Arissana",
    "Sebastião Souza Pessoa": "Sebastião",
    "MuslihaT": "MuslihaT",
    'René "Loup" Arcemont': "Loup",
    "Esâ Afontov": "Esâ",
    "Magdalene Keino-Chemutai": "Magdalene",
    'Ryō "Phoenix" Ōno': "Phoenix",
    "Lat": "Lat",
    "Dewi Subrotoputri": "Dewi",
    "Az McCaffrey": "Az",
    "Mercury": "Mercury",
    "Zahya Sadeghi": "Zahya",
    "Captain Padma Isbister": "Padma",
    'Barry "Baz" Wong': "Baz",
    # Seen in the test fixtures
    "The Catalyst": "Catalyst",
    "Nova Initiumia": "Nova",
    "Tāo Salonga": "Tāo",
    "Topan": "Topan",
}
