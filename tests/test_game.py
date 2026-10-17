# tests/test_game.py
"""/v1/game: birthdays and shared settings for the Ford House game."""
import json
import pytest
from datetime import date

from app import cli

pytestmark = pytest.mark.integration

GAME_TOKEN = "test-game-token"
URL = "/v1/game/family"


@pytest.fixture
def game_token(monkeypatch):
    monkeypatch.setenv("GAME_TOKEN", GAME_TOKEN)
    return {"Authorization": f"Bearer {GAME_TOKEN}"}


@pytest.fixture
def family(db_session, make_user, make_child):
    """Two children and two parents set up as game players, plus a
    grandparent and a third child who aren't in the game."""
    girl = make_child(name="Penelope", balance="12.50",
                      birth_date=date(2016, 3, 15))
    boy = make_child(name="Dominic", birth_date=date(2018, 6, 1))
    make_child(name="Cousin", birth_date=date(2015, 1, 1))
    mum = make_user(username="mum", display_name="Mum", role="parent")
    dad = make_user(username="dad", display_name="Dad", role="admin")
    grandad = make_user(username="grandad", role="adult")
    girl.game_key, boy.game_key = "girl", "boy"
    mum.game_key, mum.birth_date = "mum", date(1985, 5, 5)
    dad.game_key, dad.birth_date = "dad", date(1980, 1, 31)
    grandad.birth_date = date(1950, 7, 7)
    db_session.commit()
    return dad


EXPECTED = {"players": [
    {"key": "girl", "birthday": "2016-03-15"},
    {"key": "boy", "birthday": "2018-06-01"},
    {"key": "mum", "birthday": "1985-05-05"},
    {"key": "dad", "birthday": "1980-01-31"},
]}


class TestGameFamily:

    def test_no_token_returns_401(self, client, family):
        assert client.get(URL).status_code == 401

    def test_wrong_token_returns_401(self, client, family, game_token):
        resp = client.get(URL, headers={"Authorization": "Bearer nope"})

        assert resp.status_code == 401

    def test_game_token_returns_the_players(self, client, family,
                                            game_token):
        resp = client.get(URL, headers=game_token)

        assert resp.status_code == 200
        assert resp.json() == EXPECTED

    @pytest.mark.parametrize("role", ["admin", "parent", "adult", "child"])
    def test_any_family_login_works(self, client_for, make_user, family,
                                    role):
        resp = client_for(make_user(role=role)).get(URL)

        assert resp.status_code == 200
        assert resp.json() == EXPECTED

    def test_response_has_nothing_but_key_and_birthday(self, client, family,
                                                       game_token):
        body = client.get(URL, headers=game_token).text

        for private in ("Penelope", "Dominic", "Cousin", "Mum", "Dad",
                        "grandad", "12.5", "balance", "id"):
            assert private not in body

    def test_player_without_a_birthday_is_left_out(self, client, family,
                                                   game_token, db_session):
        family.birth_date = None
        db_session.commit()

        keys = [p["key"] for p in
                client.get(URL, headers=game_token).json()["players"]]

        assert keys == ["girl", "boy", "mum"]

    def test_game_token_disabled_when_not_configured(self, client, family,
                                                     monkeypatch):
        monkeypatch.delenv("GAME_TOKEN", raising=False)

        resp = client.get(URL, headers={"Authorization": "Bearer "})

        assert resp.status_code == 401

    @pytest.mark.parametrize("method,path", [
        ("get", "/v1/family-photos/feed"),
        ("get", "/v1/family-photos/users"),
        ("get", "/v1/family-photos/admin/pending"),
        ("get", "/v1/pocket-money/children"),
        ("post", "/v1/pocket-money/deposit/1?amount=1&description=x"),
        ("get", "/v1/investments/dashboard-summary"),
        ("get", "/v1/utilities/dashboard"),
        ("get", "/v1/messaging/conversations"),
    ])
    def test_game_token_is_rejected_everywhere_else(
            self, client, family, game_token, method, path):
        resp = getattr(client, method)(path, headers=game_token)

        assert resp.status_code == 401


class TestGameCli:

    @pytest.fixture(autouse=True)
    def use_test_session(self, monkeypatch, db_session):
        monkeypatch.setattr(cli, "SessionLocal", lambda: db_session)
        monkeypatch.setattr(db_session, "close", lambda: None)

    def test_set_game_parent(self, make_user, db_session):
        user = make_user(username="dad")

        cli.main(["set-game-parent", "dad", "dad", "1980-01-31"])

        db_session.refresh(user)
        assert (user.game_key, user.birth_date) == ("dad", date(1980, 1, 31))

    def test_set_game_child_keeps_the_existing_birthday(self, make_child,
                                                        db_session):
        child = make_child(name="Penelope", birth_date=date(2016, 3, 15))

        cli.main(["set-game-child", "Penelope", "girl"])

        db_session.refresh(child)
        assert (child.game_key, child.birth_date) == (
            "girl", date(2016, 3, 15))

    def test_child_cannot_be_given_a_parent_key(self, make_child):
        make_child(name="Penelope")

        with pytest.raises(SystemExit):
            cli.main(["set-game-child", "Penelope", "mum"])


SETTINGS_URL = "/v1/game/settings"
LOOK = {"skin": "#f1d1ba", "hair": "long", "hairColor": "#9b7452",
        "top": "own", "pants": "#1c1e25", "shoes": "#f2eef2",
        "glasses": False, "beard": False}
SETTINGS = {"players": {"girl": {"name": "Pia", "look": LOOK},
                        "boy": {"name": None, "look": LOOK}},
            "off": ["dragon"]}


def with_change(change):
    """A copy of SETTINGS with change(copy) applied to it."""
    settings = json.loads(json.dumps(SETTINGS))
    change(settings)
    return settings


class TestGameSettings:

    def save(self, client, headers, settings=SETTINGS, base_version=0):
        return client.put(SETTINGS_URL, headers=headers, json={
            "base_version": base_version, "settings": settings})

    @pytest.mark.parametrize("method", ["get", "put"])
    def test_no_token_returns_401(self, client, method):
        resp = client.request(method, SETTINGS_URL, json={
            "base_version": 0, "settings": SETTINGS})

        assert resp.status_code == 401

    @pytest.mark.parametrize("method", ["get", "put"])
    def test_wrong_token_returns_401(self, client, game_token, method):
        resp = client.request(
            method, SETTINGS_URL, headers={"Authorization": "Bearer nope"},
            json={"base_version": 0, "settings": SETTINGS})

        assert resp.status_code == 401

    def test_parent_login_can_read_and_save(self, parent_client):
        assert self.save(parent_client, {}).status_code == 200
        assert parent_client.get(SETTINGS_URL).json()["version"] == 1

    def test_before_any_save_there_are_no_settings(self, client,
                                                   game_token):
        resp = client.get(SETTINGS_URL, headers=game_token)

        assert resp.status_code == 200
        assert resp.json() == {"version": 0, "updated_at": None,
                               "settings": None}

    def test_save_increments_the_version_and_reads_back(self, client,
                                                        game_token):
        first = self.save(client, game_token)
        changed = with_change(lambda s: s["off"].append("bike"))
        second = self.save(client, game_token, changed, base_version=1)

        assert first.status_code == 200
        assert first.json()["version"] == 1
        assert second.status_code == 200
        assert second.json()["version"] == 2
        got = client.get(SETTINGS_URL, headers=game_token).json()
        assert got == second.json()
        assert got["settings"] == changed
        assert got["updated_at"] is not None

    def test_old_base_version_returns_409_with_the_current_settings(
            self, client, game_token):
        self.save(client, game_token)
        newer = with_change(lambda s: s["off"].clear())
        self.save(client, game_token, newer, base_version=1)

        resp = self.save(client, game_token, base_version=1)

        assert resp.status_code == 409
        assert resp.json()["version"] == 2
        assert resp.json()["settings"] == newer
        got = client.get(SETTINGS_URL, headers=game_token).json()
        assert (got["version"], got["settings"]) == (2, newer)

    def test_first_save_with_a_base_version_returns_409(self, client,
                                                        game_token):
        resp = self.save(client, game_token, base_version=3)

        assert resp.status_code == 409
        assert resp.json()["version"] == 0
        assert resp.json()["settings"] is None

    def test_colours_and_names_are_tidied(self, client, game_token):
        settings = with_change(lambda s: s["players"]["girl"].update(
            name="  Zoë ", look={**LOOK, "skin": "#F1D1BA"}))

        saved = self.save(client, game_token, settings).json()["settings"]

        assert saved["players"]["girl"]["name"] == "Zoë"
        assert saved["players"]["girl"]["look"]["skin"] == "#f1d1ba"

    def test_partial_look_and_missing_players_are_accepted(
            self, client, game_token):
        settings = {"players": {"dad": {"look": {"beard": True}}},
                    "off": []}

        resp = self.save(client, game_token, settings)

        assert resp.status_code == 200
        assert resp.json()["settings"] == settings

    def test_swapped_rooms_are_kept(self, client, game_token):
        settings = with_change(lambda s: s.update(swapRooms=True))

        resp = self.save(client, game_token, settings)

        assert resp.status_code == 200
        assert resp.json()["settings"]["swapRooms"] is True
        got = client.get(SETTINGS_URL, headers=game_token).json()
        assert got["settings"] == settings

    @pytest.mark.parametrize("change", [
        lambda s: s["players"]["girl"].update(name="<b>Pia</b>"),
        lambda s: s["players"]["girl"].update(name="A" * 17),
        lambda s: s["players"]["girl"].update(name="Pia_"),
        lambda s: s["players"]["girl"].update(name="   "),
        lambda s: s["players"]["girl"].update(name=5),
        lambda s: s["players"].update(grandad={"name": "G"}),
        lambda s: s["players"]["girl"]["look"].update(hat="red"),
        lambda s: s["players"]["girl"]["look"].update(skin="red"),
        lambda s: s["players"]["girl"]["look"].update(skin=None),
        lambda s: s["players"]["girl"]["look"].update(top="#12345"),
        lambda s: s["players"]["girl"]["look"].update(hair="mohican"),
        lambda s: s["players"]["girl"]["look"].update(glasses="yes"),
        lambda s: s["players"]["girl"].update(birthday="2016-03-15"),
        lambda s: s.update(off=["dragon", "lawn"]),
        lambda s: s.update(off=["dragon", "dragon"]),
        lambda s: s.update(birthdays={"girl": "2016-03-15"}),
        lambda s: s.pop("players"),
        lambda s: s.update(swapRooms="yes"),
        lambda s: s.update(swapRooms=None),
    ], ids=["markup in a name", "name over 16", "underscore in a name",
            "blank name", "name not text", "unknown player",
            "unknown look field", "bad colour", "null colour",
            "bad top colour", "unknown hair", "glasses not a bool",
            "extra player field", "unknown job group",
            "repeated job group", "extra top-level key", "no players",
            "swapRooms not a bool", "null swapRooms"])
    def test_invalid_settings_return_422_and_save_nothing(
            self, client, game_token, change):
        resp = self.save(client, game_token, with_change(change))

        assert resp.status_code == 422
        got = client.get(SETTINGS_URL, headers=game_token).json()
        assert got["version"] == 0

    @pytest.mark.parametrize("body", [
        {"base_version": "0", "settings": SETTINGS},
        {"base_version": -1, "settings": SETTINGS},
        {"base_version": 0},
        {"base_version": 0, "settings": SETTINGS, "extra": 1},
    ])
    def test_invalid_request_body_returns_422(self, client, game_token,
                                              body):
        resp = client.put(SETTINGS_URL, headers=game_token, json=body)

        assert resp.status_code == 422

    def test_body_over_8_kb_returns_413(self, client, game_token):
        resp = client.put(SETTINGS_URL, headers=game_token, json={
            "base_version": 0, "settings": SETTINGS, "pad": "x" * 8200})

        assert resp.status_code == 413

    def test_more_than_30_saves_a_minute_returns_429(self, client,
                                                     game_token):
        for version in range(30):
            resp = self.save(client, game_token, base_version=version)
            assert resp.status_code == 200

        resp = self.save(client, game_token, base_version=30)

        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    def test_reading_is_not_rate_limited(self, client, game_token):
        for _ in range(35):
            resp = client.get(SETTINGS_URL, headers=game_token)

        assert resp.status_code == 200
