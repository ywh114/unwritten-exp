"""Preview tests — pin resolution merges correctly, is deterministic, and
round-trips through the M0 Node JSON shape."""

from __future__ import annotations

import json
import pathlib

import pytest

from exp.k13_treegen.content import load_content
from exp.k13_treegen.model import Node
from exp.k13_treegen.preview import gloss, preview_record, resolve_pin

CONTENT = pathlib.Path(__file__).parent / "content"


@pytest.fixture(scope="module")
def pack():
    return load_content(CONTENT)


def test_pin_overrides_win(pack):
    tiger = resolve_pin(pack, "tiger")
    # pin overrides
    assert tiger.axes["base_color"] == "orange"
    assert tiger.axes["body_mass"] == 220.0
    assert tiger.axes["pupil_shape"] == "round"   # knobs override lands too
    # preset inheritance
    assert tiger.generics["covering"] == "fur"
    assert tiger.axes["pattern_motif"] == "striped"
    assert tiger.plan == "tetrapod" and tiger.preset == "tetrapod.cat"


def test_deterministic_sid_and_json(pack):
    a = json.dumps(preview_record(pack, "tiger", seed=0), sort_keys=True)
    b = json.dumps(preview_record(pack, "tiger", seed=0), sort_keys=True)
    assert a == b
    # different label -> different stable id
    assert (resolve_pin(pack, "tiger").sid
            != resolve_pin(pack, "wolf").sid)


def test_node_json_round_trip(pack):
    n = resolve_pin(pack, "coal-rat")
    assert Node.from_json(n.to_json()).to_json() == n.to_json()


def test_gloss_is_one_line(pack):
    g = gloss(pack, "tiger")
    assert "\n" not in g and "tiger" in g and "striped" in g
