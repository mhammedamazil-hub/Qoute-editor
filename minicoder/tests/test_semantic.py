from minicoder import semantic


def test_concept_dedup_and_relations(brain_home):
    a = semantic.add_concept("CSS flexbox", confidence=0.6)
    b = semantic.add_concept("CSS flexbox", confidence=0.9)  # same label → same id, confidence raised
    assert a == b
    semantic.add_concept("overflow hidden", confidence=0.7)
    semantic.add_relation("CSS flexbox", "overflow hidden", "solves", confidence=0.8)
    hood = semantic.neighbourhood("flexbox", depth=1)
    assert hood["found"] and any(n["label"] == "overflow hidden" for n in hood["nodes"])


def test_graph_payload_shape(brain_home):
    semantic.add_concept("Python")
    semantic.add_concept("GIL")
    semantic.add_relation("Python", "GIL", "depends_on")
    payload = semantic.graph_payload(limit=10)
    assert payload["total_nodes"] >= 2 and payload["total_edges"] >= 1


def test_unknown_relation_rejected(brain_home):
    try:
        semantic.add_relation("a", "b", "teleports_to")
        assert False
    except ValueError:
        pass
