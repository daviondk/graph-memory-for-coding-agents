def direct_source():
    return 2


def global_source():
    return 2


def chain_source():
    return 2


def mapping_source():
    return 2


def default_source():
    return 2


def class_source():
    return 2


def register_source():
    return 2


def dynamic_source():
    return 2


def unused_source():
    return 2


GLOBAL_VALUE = global_source()
CHAIN_FIRST = chain_source()
CHAIN_SECOND = CHAIN_FIRST + 1
MAPPING = {"value": mapping_source()}


def default_value(value=default_source()):
    return value


class Values:
    value = class_source()


TABLE = {}


def install(value):
    TABLE["value"] = value


install(register_source())
DYNAMIC_VALUE = dynamic_source()
UNUSED_VALUE = unused_source()


def direct():
    return direct_source()


def global_value():
    return GLOBAL_VALUE


def chain():
    return CHAIN_SECOND - 1


def mapping():
    return MAPPING["value"]


def class_value():
    return Values.value


def registered():
    return TABLE["value"]


def dynamic():
    return globals()["DYNAMIC_VALUE"]


def unchanged():
    return 2

