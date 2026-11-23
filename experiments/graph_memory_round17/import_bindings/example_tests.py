import example_library as lib


def test_direct():
    assert lib.direct() == 2


def test_global():
    assert lib.global_value() == 2


def test_chain():
    assert lib.chain() == 2


def test_mapping():
    assert lib.mapping() == 2


def test_default():
    assert lib.default_value() == 2


def test_class():
    assert lib.class_value() == 2


def test_register():
    assert lib.registered() == 2


def test_dynamic():
    assert lib.dynamic() == 2


def test_unaffected():
    assert lib.unchanged() == 2


def test_constant():
    assert 3 + 5 == 8

