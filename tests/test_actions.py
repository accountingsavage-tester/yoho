import pytest

from tools.system import ActionParseError, ActionType, parse_action


def elements():
    return [
        {"label": "Button", "clickable": True, "enabled": True, "focusable": False, "editable": False},
        {"label": "Input", "clickable": False, "enabled": True, "focusable": True, "editable": True},
        {"label": "Text", "clickable": False, "enabled": True, "focusable": False, "editable": False},
        {"label": "Disabled", "clickable": True, "enabled": False, "focusable": False, "editable": False},
    ]


def test_valid_actions():
    assert parse_action("ACTION: TAP 1", elements()).value == 1
    assert parse_action("ACTION: TYPE 2 hello world", elements()).value == (2, "hello world")
    assert parse_action("ACTION: SWIPE up").value == "up"
    assert parse_action("ACTION: KEYEVENT 4").value == 4
    assert parse_action("ACTION: HOME").type is ActionType.HOME
    assert parse_action("ACTION: BACK").type is ActionType.BACK
    assert parse_action("ACTION: SAY hello").value == "hello"

@pytest.mark.parametrize("value", ["ACTION: TAP", "ACTION: TAP abc", "ACTION: TAP 999999"])
def test_invalid_tap(value):
    with pytest.raises(ActionParseError): parse_action(value, elements())


def test_tap_must_be_clickable():
    with pytest.raises(ActionParseError): parse_action("ACTION: TAP 2", elements())

@pytest.mark.parametrize("value", ["ACTION: TYPE", "ACTION: TYPE 3 hello", "ACTION: TYPE 2"])
def test_invalid_type(value):
    with pytest.raises(ActionParseError): parse_action(value, elements())

@pytest.mark.parametrize("value", ["ACTION: SWIPE diagonal", "ACTION: SWIPE", "ACTION: SWIPE up extra"])
def test_invalid_swipe(value):
    with pytest.raises(ActionParseError): parse_action(value)

@pytest.mark.parametrize("value", ["ACTION: KEYEVENT x", "ACTION: KEYEVENT -1", "ACTION: KEYEVENT"])
def test_invalid_keyevent(value):
    with pytest.raises(ActionParseError): parse_action(value)

@pytest.mark.parametrize("value", ["ACTION: NOPE 1", "", "hello\nACTION: HOME", "ACTION: HOME\nACTION: BACK", "ACTION: HOME now", "ACTION: SAY"])
def test_malformed_or_unknown(value):
    with pytest.raises(ActionParseError): parse_action(value)
