import pytest


@pytest.mark.contract
def test_cf_8_reviews_can_be_marked_complete():
    """
    CF-8: Evening review + weekly audit must support completion marking.
    Prevents spam re-prompting.
    """
    pytest.xfail("Implement review completion tracking.")
