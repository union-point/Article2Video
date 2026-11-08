import pytest

from article_video.normalization import NameMatcher, quantities


@pytest.mark.parametrize("a,b", [
    ("forty-eight out of fifty", "48/50"),
    ("ninety-one percent", "91%"),
    ("ninety-one per cent", "91%"),
    ("three thousand dollars", "$3,000"),
    ("three thousand pounds", "£3000"),
    ("four point nine", "4.9"),
    ("3–5", "three to five"),
    ("3-5", "between three and five"),
    ("5–10%", "five percent to ten percent"),
    ("$3,000–$5,000", "3000 dollars to 5000 dollars"),
    ("2.5 million", "2,500,000"),
    ("one hundred and twenty-three", "123"),
    ("first", "1st"),
    ("USD 3,000", "$3000"),
    ("3000 EUR", "three thousand euros"),
])
def test_equivalent_quantities(a, b):
    assert quantities(a) == quantities(b)


def test_units_ratios_and_entity_spelling_are_not_flattened():
    assert quantities("91%") != quantities("91")
    assert quantities("$48") != quantities("48")
    assert "ratio:48/50" in quantities("48/50") - quantities("48 and 50")
    assert quantities("-5") != quantities("5")


def test_unknown_digit_formats_do_not_silently_disappear():
    assert "unparsed:99k" in quantities("99k")
    assert quantities("99k") != quantities("100k")
    assert "unparsed:2.26.0" in quantities("2.26.0")


def test_aliases_possessives_case_punctuation_and_unknown_names():
    matcher = NameMatcher(["Searchbloom", "iPullRank"], {"Searchbloom": ["Search Bloom"]})
    assert not matcher.missing("Searchbloom's score", ["Search Bloom has a score."])
    assert not matcher.missing("IPULLRANK", ["iPullRank"])
    assert "FakeCorp" in matcher.missing("FakeCorp scored well.", ["Searchbloom scored well."])
    assert matcher.missing("Acme", ["Acmeology"]) == ["Acme"]
