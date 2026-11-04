"""clean.py: each removal rule, duplicates, id order and a stable checksum."""
import hashlib
import json

import clean

INTENTS = clean.load_intents()


def rec(i, text, raw):
    return {"id": f"C{i:04d}", "text": text, "teacher_raw": raw}


def good(intent="weather_query", date=None, time=None, place=None):
    return json.dumps({"intent": intent, "date": date, "time": time, "place": place})


RECORDS = [
    rec(5, "weather in london", good(place="london")),                       # kept
    rec(2, "set alarm for six am", '{"intent": "alarm_set", "date": '),     # (a) broken JSON
    rec(3, "set alarm", json.dumps({"intent": "alarm_set", "date": None, "time": None})),  # (b)
    rec(4, "play music", good(intent="music_play")),                        # (c)
    rec(6, "wake me at six am", good(intent="alarm_set", time="06:00")),  # (d) converted value
    rec(7, "what is on today", good(intent="calendar_query", date="tomorrow")),  # (d) invented
    rec(1, "weather in london", good(place="london")),                       # same text, smaller id
    rec(8, "whats up", good(intent="calendar_query", place="at")),           # (d) "at" is not a whole word here
]


def test_counts_add_up_and_each_rule_fires():
    kept, c = clean.clean(RECORDS, INTENTS)
    assert c["input"] == 8
    assert (c["a_invalid_json"], c["b_wrong_keys"], c["c_bad_intent"]) == (1, 1, 1)
    assert c["d_bad_slot"] == 3 and c["duplicates"] == 1 and c["kept"] == 1
    assert c["input"] == sum(v for k, v in c.items() if k != "input")


def test_duplicate_keeps_smallest_id():
    kept, _ = clean.clean(RECORDS, INTENTS)
    assert [r["id"] for r in kept] == ["C0001"]


def test_slot_must_appear_as_whole_words():
    assert clean.slot_in_command("seven am", "wake me at Seven  AM please")
    assert not clean.slot_in_command("at", "what is the weather")
    assert not clean.slot_in_command("", "anything")
    assert not clean.slot_in_command(7, "seven")


def test_output_is_sorted_and_checksum_stable():
    shuffled = list(reversed(RECORDS))
    a = clean.serialise(clean.clean(RECORDS, INTENTS)[0])
    b = clean.serialise(clean.clean(shuffled, INTENTS)[0])
    assert hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest()
    assert a.endswith(b"\n") and b"\r" not in a
