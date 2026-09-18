from app.engine import refcode


def test_shape_and_roundtrip():
    code = refcode.generate()
    assert len(code) == 14 and code.count("-") == 2
    assert refcode.is_wellformed(code)
    assert refcode.digest(code, "s") == refcode.digest(code.lower().replace("-", " "), "s")


def test_secret_matters_and_code_not_in_digest():
    code = refcode.generate()
    assert refcode.digest(code, "a") != refcode.digest(code, "b")
    assert refcode.normalise(code) not in refcode.digest(code, "a").upper()


def test_lookalike_characters_are_forgiven():
    assert refcode.normalise("O0Il-1111-2222") == "00111111" + "2222"


def test_rejects_garbage():
    assert not refcode.is_wellformed("hello")
    assert not refcode.is_wellformed("")
