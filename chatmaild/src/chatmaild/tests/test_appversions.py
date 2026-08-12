import json

import pytest

from chatmaild.metadata import MetadataDictProxy

ALLOWED_URL_PREFIXES = (
    "https://github.com/deltachat/",
    "https://download.delta.chat/",
)


def check_string(value):
    assert isinstance(value, str), value
    assert value


def check_version_integer(value):
    # core parses this as u32, see https://github.com/chatmail/core/pull/8557
    assert isinstance(value, int) and not isinstance(value, bool), value
    assert 0 <= value < 2**32, value


def check_appversions(data):
    """Verifies the file the way core parses it.

    core deserializes into typed structs and drops the whole payload
    of a relay if a single value has an unexpected type,
    while missing or misspelled keys silently turn into defaults.
    """
    assert set(data) == {"clients"}, data
    assert isinstance(data["clients"], list)
    assert data["clients"]
    client_ids = []
    for client in data["clients"]:
        assert set(client) == {"clientId", "sources"}, client
        check_string(client["clientId"])
        client_ids.append(client["clientId"])
        assert isinstance(client["sources"], list)
        assert client["sources"]
        source_ids = []
        for source in client["sources"]:
            assert set(source) == {
                "sourceId",
                "versionInteger",
                "versionString",
                "downloadUrl",
            }, source
            check_string(source["sourceId"])
            source_ids.append(source["sourceId"])
            check_version_integer(source["versionInteger"])
            check_string(source["versionString"])
            check_string(source["downloadUrl"])
            assert source["downloadUrl"].startswith(ALLOWED_URL_PREFIXES)
        # core takes the first matching source, later duplicates never surface
        assert len(set(source_ids)) == len(source_ids), source_ids
    assert len(set(client_ids)) == len(client_ids), client_ids


@pytest.fixture
def appversions():
    # check the file which chatmail-metadata actually serves
    path = MetadataDictProxy(notifier=None, metadata=None).appversions_path
    return json.loads(path.read_text())


def test_appversions_schema(appversions):
    check_appversions(appversions)


@pytest.mark.parametrize("value", [True, -1, 2**32, "754", 754.0, None])
def test_version_integer_rejected(appversions, value):
    appversions["clients"][0]["sources"][0]["versionInteger"] = value
    with pytest.raises(AssertionError):
        check_appversions(appversions)


@pytest.mark.parametrize("key", ["clientId", "sources"])
def test_misspelled_client_key_rejected(appversions, key):
    client = appversions["clients"][0]
    client[key + "s"] = client.pop(key)
    with pytest.raises(AssertionError):
        check_appversions(appversions)


def test_duplicate_source_id_rejected(appversions):
    sources = appversions["clients"][0]["sources"]
    sources.append(dict(sources[0]))
    with pytest.raises(AssertionError):
        check_appversions(appversions)


def test_foreign_download_url_rejected(appversions):
    appversions["clients"][0]["sources"][0]["downloadUrl"] = "https://example.org/x.apk"
    with pytest.raises(AssertionError):
        check_appversions(appversions)
