"""MoSPI eSankhyiki state names map to census state codes."""

from pipeline.sources.mospi import fips_of


def test_state_names():
    assert fips_of("Kerala") == "32"
    assert fips_of("Andaman & Nicobar Islands") == "35"
    assert fips_of("Jammu & Kashmir") == "01"
    assert fips_of("All India") == "IN"
    # one UT since 2020, under either spelling
    assert fips_of("Dadra & Nagar Haveli and Daman & Diu") == "26"
    assert fips_of("Dadra & Nagar Haveli") == "26"
    assert fips_of("Atlantis") is None
