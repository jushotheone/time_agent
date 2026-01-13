import pytest
import beia_core.models.timebox as tb
from beia_core.models.enums import Domain


@pytest.mark.contract
def test_inv_3_domain_enum_contains_required_values():
    required = {"loj", "telnwa", "dev", "client", "music"}
    actual = {d.name for d in Domain}
    missing = required - actual
    assert not missing, f"Missing required Domain enum values: {sorted(missing)}"


@pytest.mark.contract
def test_inv_1_no_silent_data_loss_requires_audit_or_revision_trail():
    """
    Canonical contract: edits must be auditable (immutable or versioned).
    Your current DB layer overwrites rows (update_segment), with no audit trail table.
    So: we mark this as expected fail until you implement revisions/audit.

    Suggested fix:
      - Add segments_revisions table OR
      - Add audit_log table + trigger OR
      - Make updates append-only (new row version)
    """
    pytest.xfail("Audit/versioning not implemented yet (INV-1). Add revision/audit trail then make this pass.")


@pytest.mark.contract
def test_inv_2_chat_first_control_no_ui_dependency_is_not_met_yet():
    """
    Canonical contract: every action must be executable by text only.
    Your code still uses InlineKeyboard callbacks as a core control layer.

    We xfail here until you implement:
      - deterministic text protocol commands (DONE/SKIP/RESCHEDULE etc.)
      - and treat Telegram UI as optional sugar, not required
    """
    pytest.xfail("Chat-only control not enforced yet (INV-2). Implement deterministic commands + remove UI dependency.")