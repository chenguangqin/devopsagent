from devopsagent.runners.base import budget_note


def test_budget_note_reports_remaining_steps():
    note = budget_note(5, 40)

    assert "[step 5/40, 35 left]" in note
    assert "Budget is low" not in note


def test_budget_note_warns_when_budget_is_low():
    assert "Budget is low" in budget_note(30, 40)
    assert "Budget is low" in budget_note(10, 12)
    assert "0 left" in budget_note(45, 40)
