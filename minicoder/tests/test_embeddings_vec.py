import numpy as np
from minicoder.embeddings import embed_text, cosine, to_blob, from_blob
from minicoder.vecstore import upsert_vector, search_vectors
from minicoder.db import connect


def test_semantic_nearness(brain_home):
    a = embed_text("flexbox overflow CSS layout bug")
    b = embed_text("CSS flexbox overflow layout issue")
    c = embed_text("quantum entanglement neutron star")
    assert cosine(a, b) > cosine(a, c)


def test_blob_roundtrip(brain_home):
    v = embed_text("hello minicoder")
    assert np.allclose(from_blob(to_blob(v)), v)


def test_vector_search_returns_best(brain_home):
    with connect() as con:
        upsert_vector(con, "doc1", "concept", embed_text("python asyncio event loop"))
        upsert_vector(con, "doc2", "concept", embed_text("chocolate cake recipe"))
        hits = search_vectors(con, embed_text("asyncio python"), kind="concept", top_k=1)
    assert hits and hits[0][0] == "doc1"
