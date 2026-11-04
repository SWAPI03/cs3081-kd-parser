"""Helpers in service/inference.py that do not need a model."""
import inference


def test_first_object_cuts_after_closing_brace():
    assert inference.first_object(' {"a": "x}y", "b": {"c": 1}} trailing') == ' {"a": "x}y", "b": {"c": 1}}'
    assert inference.first_object("no object") == "no object"
    assert inference.first_object('{"open": ') == '{"open": '


def test_prompt_format_matches_training():
    assert inference.prompt_for("hi") == "Command: hi\nJSON:"
