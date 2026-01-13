import pytest


@pytest.mark.contract
def test_cf_6_edits_create_audit_trail_or_versioned_rows():
    """
    CF-6: Every edit must be auditable.
    Either append-only with versions, or audit_log table.
    """
    pytest.xfail("Implement audit trail or versioning.")
