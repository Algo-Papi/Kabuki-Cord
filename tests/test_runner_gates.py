from nhi_zues.runner import _approval_gate_reason, _requires_approval


def test_full_auto_still_requires_approval_when_channel_auto_is_off():
    assert _requires_approval("full_auto", "conversation", auto_respond_enabled=False)
    assert (
        _approval_gate_reason("full_auto", "conversation", auto_respond_enabled=False)
        == "Auto is off for this channel"
    )


def test_full_auto_allows_conversation_when_channel_auto_is_on():
    assert not _requires_approval("full_auto", "conversation", auto_respond_enabled=True)
    assert _approval_gate_reason("full_auto", "conversation", auto_respond_enabled=True) == ""


def test_live_fire_explains_universal_review_gate():
    assert _requires_approval("live_fire", "direct", auto_respond_enabled=True)
    assert (
        _approval_gate_reason("live_fire", "direct", auto_respond_enabled=True)
        == "Live Fire requires review for every draft"
    )
