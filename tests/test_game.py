# tests/test_game.py
"""GET /v1/game/family: birthdays for the Ford House game."""
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
