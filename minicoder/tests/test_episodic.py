from minicoder import episodic


def test_record_and_recall(brain_home):
    ep = episodic.record_episode(situation="Fixed the flexbox overflow on the dashboard",
                                 modality="vision", result="overflow axis swapped to hidden",
                                 verification_status="VERIFIED", lessons=["check parent min-width"],
                                 tags=["css", "ui"], confidence=0.8, source="visual_inspection")
    assert ep.id.startswith("ep_")
    got = episodic.get_episode(ep.id)
    assert got is not None and got.access_count == 1
    hits = episodic.search_episodes("flexbox overflow dashboard", top_k=3)
    assert hits and hits[0][0].id == ep.id


def test_provenance_logged(brain_home):
    from minicoder.db import connect
    ep = episodic.record_episode(situation="provenance check", source="user_instruction")
    with connect() as con:
        row = con.execute("SELECT source FROM provenance WHERE entity_id=?", (ep.id,)).fetchone()
    assert row["source"] == "user_instruction"


def test_archive_hides_from_default_listing(brain_home):
    ep = episodic.record_episode(situation="archive me", confidence=0.1)
    episodic.archive_episodes([ep.id])
    assert all(e.id != ep.id for e in episodic.list_episodes())
    assert any(e.id == ep.id for e in episodic.list_episodes(include_archived=True))
