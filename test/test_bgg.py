# coding: utf-8
from __future__ import unicode_literals

import logging
import os
import threading
import tempfile
import pytest
import xml.etree.ElementTree as ET
import pickle
import time


from boardgamegeek import BoardGameGeek, BoardGameGeekError
from boardgamegeek.api import BoardGameGeekNetworkAPI
from boardgamegeek.collection import Collection
from boardgamegeek.games import CollectionBoardGame
from boardgamegeek.hotitems import HotItems, HotItem
from boardgamegeek.plays import PlaySession, Plays
from boardgamegeek.things import Thing
from boardgamegeek.utils import DictObject


import boardgamegeek.utils as bggutil
import datetime

progress_called = False


# Kinda hard to test without having a "test" user
TEST_VALID_USER = "fagentu007"
TEST_VALID_USER_ID = 818216
TEST_USER_WITH_LOTS_OF_FRIENDS = "Solamar"        # user chosen randomly (..after a long search :)) ), just needed
                                                  # someone with lots of friends :D
TEST_INVALID_USER = "someOneThatHopefullyWontExistPlsGuysDontCreateThisUser"
TEST_INVALID_GAME_NAME = "blablablathisgamewonteverexist"
TEST_GAME_NAME = "Agricola"
TEST_GAME_ID = 31260



#TEST_GAME_NAME_2 = "Merchant of Venus (second edition)"
#TEST_GAME_ID_2 = 131646

TEST_GAME_NAME_2 = "Advanced Third Reich"
TEST_GAME_ID_2 = 283

TEST_GUILD_ID = 1229
TEST_GUILD_ID_2 = 930


if os.getenv("TRAVIS"):
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)


@pytest.fixture
def xml():
    xml_code = """
    <root>
        <node1 attr="hello1" int_attr="1">text</node1>
        <node2 attr="hello2" int_attr="2" />
        <list>
            <li attr="elem1" int_attr="1" />
            <li attr="elem2" int_attr="2" />
            <li attr="elem3" int_attr="3" />
            <li attr="elem4" int_attr="4" />
        </list>
    </root>
    """
    return ET.fromstring(xml_code)




@pytest.fixture
def bgg():
    return BoardGameGeek(cache=None, retries=0, retry_delay=0)  # disable retrying for testing

@pytest.fixture
def null_logger():
    # create logger
    logger = logging.getLogger("null")
    logger.setLevel(logging.ERROR)
    return logger


def progress_cb(items, total):
    global progress_called
    logging.debug("progress_cb: fetched {} items out of {}".format(items, total))
    progress_called = True


#
# Test caches
#
def test_no_caching():
    # test that we can disable caching
    bgg = BoardGameGeek(cache=None)

    user = bgg.user(TEST_VALID_USER)

    assert user is not None
    assert user.name == TEST_VALID_USER


def test_sqlite_caching():
    # test that we can use the SQLite cache
    # generate a temporary file
    fd, name = tempfile.mkstemp(suffix=".cache")

    # close the file and unlink it, we only need the temporary name
    os.close(fd)
    os.unlink(name)

    assert not os.path.isfile(name)

    with pytest.raises(BoardGameGeekError):
        # invalid value for the ttl parameter
        BoardGameGeek(cache="sqlite://{}?ttl=blabla&fast_save=0".format(name))

    with pytest.raises(BoardGameGeekError):
        BoardGameGeek(cache="invalid://cache")

    bgg = BoardGameGeek(cache="sqlite://{}?ttl=1000".format(name))

    user = bgg.user(TEST_VALID_USER)
    assert user is not None
    assert user.name == TEST_VALID_USER

    assert os.path.isfile(name)

    # clean up..
    os.unlink(name)



#region user() testing
def test_get_user_with_invalid_parameters(bgg):
    # test how the module reacts to unexpected parameters
    for invalid in [None, ""]:
        with pytest.raises(BoardGameGeekError):
            bgg.user(invalid)


def test_get_invalid_user_info(bgg):

    global progress_called

    progress_called = False
    user = bgg.user(TEST_INVALID_USER, progress=progress_cb)

    assert user is None
    assert not progress_called


def test_get_valid_user_info(bgg, null_logger):
    global progress_called

    progress_called = False
    user = bgg.user(TEST_USER_WITH_LOTS_OF_FRIENDS, progress=progress_cb)

    assert user is not None
    assert user.name == TEST_USER_WITH_LOTS_OF_FRIENDS
    assert type(user.id) == int
    assert progress_called

    assert type(user.buddies) == list
    assert type(user.guilds) == list
    assert type(user.last_login) == datetime.datetime

    str(user)
    repr(user)

    for buddy in user.buddies:
        str(buddy)
        repr(buddy)

    for guild in user.guilds:
        repr(guild)

    for i in user.top10:
        repr(i)
        assert i.id >= 0
        assert i.name is not None

    for i in user.hot10:
        repr(i)
        assert i.id >= 0
        assert i.name is not None

    # for coverage's sake
    user._format(null_logger)
    assert type(user.data()) == dict
#endregion

#region collection() testing
def test_get_collection_with_invalid_parameters(bgg):
    for invalid in [None, ""]:
        with pytest.raises(BoardGameGeekError):
            bgg.collection(invalid)


def test_get_invalid_users_collection(bgg):
    collection = bgg.collection(TEST_INVALID_USER)
    assert collection is None


def test_get_valid_users_collection(bgg, null_logger):
    collection = bgg.collection(TEST_VALID_USER)

    assert collection is not None
    assert collection.owner == TEST_VALID_USER
    assert type(len(collection)) == int
    assert type(collection.items) == list

    # make sure we can iterate through the collection
    for g in collection:
        assert type(g.id) == int
        repr(g)

    str(collection)
    repr(collection)

    # for coverage's sake
    collection._format(null_logger)
    assert type(collection.data()) == dict


def test_creating_collection_out_of_raw_data():
    # test raise exception if invalid items given
    with pytest.raises(BoardGameGeekError):
        Collection({"items": [{"id": 102}]})

    # test that items are added to the collection from the constructor
    c = Collection({"owner": "me", "items": [
        {"id": 100, "name": "foobar"}
    ]})

    assert len(c) == 1
    assert c.owner == "me"
    assert type(c[0]) == CollectionBoardGame
    assert c[0].id == 100
    assert c[0].name == "foobar"

    with pytest.raises(BoardGameGeekError):
        # raises exception on invalid game data
        c.add_game({"bla": "bla"})
#endregion

#region guild() testing
def test_get_guild_with_invalid_parameters(bgg):
    # test how the module reacts to unexpected parameters
    for invalid in [None, [], {}]:
        with pytest.raises(BoardGameGeekError):
            bgg.guild(invalid)


def test_get_valid_guild_info(bgg, null_logger):
    global progress_called

    progress_called = False
    # Test with a guild with a big number members so that we can cover the code that fetches the next pages
    guild = bgg.guild(TEST_GUILD_ID, progress=progress_cb)

    assert progress_called
    assert guild.id == TEST_GUILD_ID
    assert guild.name == "Geek Tools"

    assert guild.addr1 is None
    assert guild.addr2 is None
    assert guild.address is None

    for member in guild:
        pass

    repr(guild)

    assert len(guild) > 0

    # for coverage's sake
    guild._format(null_logger)
    assert type(guild.data()) == dict

    # try to fetch a guild that also has an address besides members :D
    guild = bgg.guild(TEST_GUILD_ID_2)

    assert guild.id == TEST_GUILD_ID_2
    assert guild.addr1 is not None
    assert guild.addr2 is not None
    assert guild.address == "{} {}".format(guild.addr1, guild.addr2)


def test_get_invalid_guild_info(bgg):
    global progress_called

    progress_called = False
    guild = bgg.guild(0, progress=progress_cb)

    assert guild is None
    assert not progress_called
#endregion


#region game() testing
def test_get_unknown_game_info(bgg):
    game = bgg.game(TEST_INVALID_GAME_NAME)
    assert game is None


def test_get_game_with_invalid_parameters(bgg):
    with pytest.raises(BoardGameGeekError):
        bgg.game(name=None, game_id=None)

    for invalid in [None, ""]:
        with pytest.raises(BoardGameGeekError):
            bgg.game(invalid)

    for invalid in [None, "", "asd"]:
        with pytest.raises(BoardGameGeekError):
            bgg.game(None, game_id=invalid)


def check_game(game):
    assert game is not None
    assert game.name == TEST_GAME_NAME
    assert game.id == TEST_GAME_ID
    assert game.year == 2007
    assert game.mechanics == ["Area Enclosure", "Card Drafting", "Hand Management", "Worker Placement"]
    assert game.min_players == 1
    assert game.max_players == 5
    assert game.thumbnail == "http://cf.geekdo-images.com/images/pic259085_t.jpg"
    assert game.image == "http://cf.geekdo-images.com/images/pic259085.jpg"
    assert game.playing_time > 100
    assert game.min_age == 12

    assert "Economic" in game.categories
    assert "Farming" in game.categories

    assert game.families == ["Agricola", "Animals: Cattle", "Animals: Sheep", "Harvest Series", "Solitaire Games", "Tableau Building"]

    assert game.designers == ["Uwe Rosenberg"]

    assert "Lookout Games" in game.publishers
    assert "Compaya.hu - Gamer Café Kft." in game.publishers

    assert u"Агрикола" in game.alternative_names
    assert u"아그리콜라" in game.alternative_names

    # some not so exact assertions
    assert game.users_rated >= 34000
    assert 0.0 <= game.rating_average <= 10.0
    assert 0.0 <= game.rating_bayes_average <= 10.0

    assert type(game.rating_stddev) == float
    assert type(game.rating_median) == float
    assert game.rating_num_weights >= 0
    assert type(game.rating_average_weight) == float

    assert type(game.boardgame_rank) == int

    # make sure no exception gets thrown
    repr(game)


def test_get_known_game_info(bgg, null_logger):
    # use an older game that's not so likely to change
    game = bgg.game(TEST_GAME_NAME)

    check_game(game)

    # for coverage's sake
    game._format(null_logger)

    assert type(game.data()) == dict


def test_get_known_game_info_by_id(bgg):
    game = bgg.game(None, game_id=TEST_GAME_ID)
    check_game(game)


def test_get_game_id_by_name(bgg):
    game_id = bgg.get_game_id(TEST_GAME_NAME)
    assert game_id == TEST_GAME_ID

    # Use the game "Eclipse" to test the game choosing methods
    all_eclipse_games = bgg.games("eclipse")

    game_id = bgg.get_game_id("eclipse", choose="first")
    assert game_id == all_eclipse_games[0].id

    game_id = bgg.get_game_id("eclipse", choose="recent")
    recent_year = -100000
    recent_id = None
    for g in all_eclipse_games:
        if g.year > recent_year:
            recent_id = g.id
            recent_year = g.year
    assert game_id == recent_id

    game_id = bgg.get_game_id("eclipse", choose="best-rank")
    best_rank = 1000000000
    best_id = None
    for g in all_eclipse_games:
        if g.boardgame_rank is not None and g.boardgame_rank < best_rank:
            best_id = g.id
            best_rank = g.boardgame_rank
    assert game_id == best_id

def test_get_games_by_name(bgg, null_logger):
    games = bgg.games("coup")

    for g in games:
        assert g is not None
        assert type(g.id) == int
        assert g.name == "Coup"
        g._format(null_logger)

    assert len(games) > 1
#endregion

#region search() testing
def test_search(bgg):
    res = bgg.search("some invalid game name", exact=True)
    assert not len(res)

    res = bgg.search("Twilight Struggle", exact=True)
    assert len(res)

    # test that numeric searching still works
    res = bgg.search("Agricola", search_type=BoardGameGeekNetworkAPI.SEARCH_BOARD_GAME)
    assert type(res[0].id) == int

    # test that the new type of search works
    res = bgg.search("Agricola", search_type=["boardgame"])
    assert type(res[0].id) == int

    with pytest.raises(BoardGameGeekError):
        bgg.search("Agricola", search_type=["invalid-search-type"])
#endregion

#region plays() testing
def test_get_plays_with_invalid_parameters(bgg):
    with pytest.raises(BoardGameGeekError):
        bgg.plays(name=None, game_id=None)

    with pytest.raises(BoardGameGeekError):
        bgg.plays(name="", game_id=None)

    with pytest.raises(BoardGameGeekError):
        bgg.plays(name=None, game_id="asd")


def test_get_plays_with_unknown_username_and_id(bgg):
    plays = bgg.plays(name=TEST_INVALID_USER)
    assert plays is None

    # the api is a bit weird, if the game id is invalid, it still returns some answer, but of empty size
    plays = bgg.plays(name=None, game_id=1928391829)
    assert len(plays) == 0


def test_get_plays_with_invalid_dates(bgg):
    # A string is invalid so should raise an error
    with pytest.raises(BoardGameGeekError):
        bgg.plays(name=TEST_VALID_USER, min_date="2014-01-01")

    with pytest.raises(BoardGameGeekError):
        bgg.plays(name=TEST_VALID_USER, max_date="2014-12-31")


def test_get_plays_with_valid_dates(bgg):
    min_date = datetime.date(2014, 1, 1)
    max_date = datetime.date(2014, 12, 31)
    plays = bgg.plays(TEST_VALID_USER, min_date=min_date, max_date=max_date)
    assert len(plays) > 0


def test_get_plays_of_user(bgg, null_logger):
    global progress_called

    plays = bgg.plays(name=TEST_VALID_USER, progress=progress_cb)

    assert plays.user == TEST_VALID_USER
    assert plays.user_id == TEST_VALID_USER_ID
    assert plays.game_id is None    # None since we got the plays for an user

    for p in plays.plays:
        assert type(p.id) == int
        assert p.user_id == TEST_VALID_USER_ID
        assert type(p.date) == datetime.datetime
        assert p.quantity >= 0
        assert p.duration >= 0
        assert type(p.incomplete) == bool
        assert type(p.nowinstats) == int
        assert type(p.game_id) == int
        assert type(p.game_name) == str
        assert type(p.comment) in [type(None), str]

        assert type(p.players) == list
        if p.players:
            for player in p.players:
                assert hasattr(player, "startposition")
                assert hasattr(player, "username")
                assert hasattr(player, "user_id")
                assert hasattr(player, "name")
                assert hasattr(player, "score")
                assert hasattr(player, "new")
                assert hasattr(player, "win")
                assert hasattr(player, "rating")

    plays._format(null_logger)


def test_get_plays_of_game(bgg, null_logger):
    global progress_called

    plays = bgg.plays(game_id=TEST_GAME_ID_2, progress=progress_cb)

    assert plays.user is None
    assert plays.user_id is None
    assert plays.game_id == TEST_GAME_ID_2

    for p in plays.plays:
        assert type(p.id) == int
        assert type(p.user_id) == int
        assert type(p.date) in [datetime.datetime, type(None)]
        assert p.quantity >= 0
        assert p.duration >= 0
        assert type(p.incomplete) == bool
        assert type(p.nowinstats) == int
        assert p.game_id == TEST_GAME_ID_2
        assert p.game_name == TEST_GAME_NAME_2

    plays._format(null_logger)


def test_create_plays_with_initial_data():

    with pytest.raises(BoardGameGeekError):
        Plays({"plays": [{"user_id": 10}]})

    p = Plays({"plays": [{"id": 10, "user_id": 102, "date": "2014-01-02"}]})

    assert len(p) == 1
    assert type(p[0]) == PlaySession
    assert p[0].id == 10
    assert p[0].user_id == 102
    assert type(p[0].date) == datetime.datetime
    assert p[0].date.strftime("%Y-%m-%d") == "2014-01-02"

    # it also accepts datetime objects
    now = datetime.datetime.utcnow()
    p = Plays({"plays": [{"id": 10, "user_id": 102, "date": now}]})

    assert p[0].date == now
#endregion

#region hot_items() testing
def test_get_hot_items_invalid_type(bgg):
    with pytest.raises(BoardGameGeekError):
        bgg.hot_items("invalid type")


def test_get_hot_items_boardgames(bgg, null_logger):
    for item in bgg.hot_items("boardgame"):
        assert type(item.id) == int
        assert len(item.name) > 0
        assert type(item.rank) == int
        assert type(item.year) in [int, type(None)]
        # test that all thumbnails have been fixed (http:// added)
        # note: I guess this could fail if a boardgame has no thumbnail...
        assert item.thumbnail.startswith("http://")
        item._format(null_logger)


def test_get_hot_items_boardgamepersons(bgg, null_logger):
    for item in bgg.hot_items("boardgameperson"):
        assert type(item.id) == int
        assert len(item.name) > 0
        assert type(item.rank) == int
        assert item.year is None

        item._format(null_logger)


def test_hot_items_initial_data():

    # test that exception is raised if invalid initial data is given when trying to create a HotItems object
    with pytest.raises(BoardGameGeekError):
        HotItems({"items": [{"id": 100, "name": "hotitem"}]})

    h = HotItems({"items": [{"id": 100, "name": "hotitem", "rank": 10}]})
    with pytest.raises(BoardGameGeekError):
        h.add_hot_item({"id": 100, "name": "hotitem"})

    assert type(h[0]) == HotItem
    assert len(h) == 1
    assert h[0].id == 100
    assert h[0].name == "hotitem"
    assert h[0].rank == 10
#endregion

#region Thing testing
def test_thing_creation():
    with pytest.raises(BoardGameGeekError):
        Thing({"id": 100})  # missing name

    with pytest.raises(BoardGameGeekError):
        Thing({"name": "foobar"})  # missing id

    with pytest.raises(BoardGameGeekError):
        Thing({"id": "asd", "name": "fubăr"})  # id not string

    t = Thing({"id": "10", "name": "fubăr"})

    assert t.id == 10
    assert t.name == "fubăr"
#endregion

#region Utils testing
def test_get_xml_subelement_attr(xml):

    node = bggutil.xml_subelement_attr(None, "hello")
    assert node is None

    node = bggutil.xml_subelement_attr(xml, None)
    assert node is None

    node = bggutil.xml_subelement_attr(xml, "")
    assert node is None

    node = bggutil.xml_subelement_attr(xml, "node1", attribute="attr")
    assert node == "hello1"

    node = bggutil.xml_subelement_attr(xml, "node1", attribute="int_attr", convert=int)
    assert node == 1

    # test that default works
    node = bggutil.xml_subelement_attr(xml, "node_thats_missing", default="hello")
    assert node == "hello"

    node = bggutil.xml_subelement_attr(xml, "node1", attribute="attribute_thats_missing", default=1234)
    assert node == 1234

    # test quiet
    with pytest.raises(Exception):
        # attr can't be converted to int
        node = bggutil.xml_subelement_attr(xml, "node1", attribute="attr", convert=int)

    node = bggutil.xml_subelement_attr(xml, "node1", attribute="attr", convert=int, quiet=True)
    assert node == None

    node = bggutil.xml_subelement_attr(xml, "node1", attribute="attr", convert=int, default=999, quiet=True)
    assert node == 999


def test_get_xml_subelement_attr_list(xml):

    nodes = bggutil.xml_subelement_attr_list(None, "list")
    assert nodes is None

    nodes = bggutil.xml_subelement_attr_list(xml, None)
    assert nodes is None

    nodes = bggutil.xml_subelement_attr_list(xml, "")
    assert nodes is None

    list_root = xml.find("list")
    nodes = bggutil.xml_subelement_attr_list(list_root, "li", attribute="attr")
    assert nodes == ["elem1", "elem2", "elem3", "elem4"]

    nodes = bggutil.xml_subelement_attr_list(list_root, "li", attribute="int_attr", convert=int)
    assert nodes == [1, 2, 3, 4]

    nodes = bggutil.xml_subelement_attr_list(xml, "node1", attribute="attr")
    assert nodes == ["hello1"]

    # test default
    nodes = bggutil.xml_subelement_attr_list(list_root, "li", attribute="missing_attr", default="n/a")
    assert nodes == ["n/a", "n/a", "n/a", "n/a"]

    # test quiet
    with pytest.raises(Exception):
        nodes = bggutil.xml_subelement_attr_list(list_root, "li", attribute="attr", convert=int)

    nodes = bggutil.xml_subelement_attr_list(list_root, "li", attribute="attr", convert=int, quiet=True)
    assert nodes == [None, None, None, None]

    nodes = bggutil.xml_subelement_attr_list(list_root, "li", attribute="attr", convert=int, quiet=True, default=1)
    assert nodes == [1, 1, 1, 1]


def test_get_xml_subelement_text(xml):

    node = bggutil.xml_subelement_text(None, "node1")
    assert node is None

    node = bggutil.xml_subelement_text(xml, None)
    assert node is None

    node = bggutil.xml_subelement_text(None, "")
    assert node is None

    node = bggutil.xml_subelement_text(xml, "node1")
    assert node == "text"

    # test that default is working
    node = bggutil.xml_subelement_text(xml, "node_thats_missing", default="default text")
    assert node == "default text"

    # test that quiet is working
    with pytest.raises(Exception):
        node = bggutil.xml_subelement_text(xml, "node1", convert=int)

    node = bggutil.xml_subelement_text(xml, "node1", convert=int, quiet=True)
    assert node == None

    node = bggutil.xml_subelement_text(xml, "node1", convert=int, quiet=True, default="asd")
    assert node == "asd"


@pytest.mark.serialize
def test_serialization():
    dummy_plays = Thing({"id": "10", "name": "fubar"})

    s = pickle.dumps(dummy_plays)
    assert s is not None

    dummy_unserialized = pickle.loads(s)
    assert type(dummy_unserialized) == Thing


def test_rate_limiting_for_requests():
    # create two threads, give each a list of games to fetch, disable cache and time the amount needed to
    # fetch the data. requests should be serialized, even if made from two different threads

    test_set_1 = [5,    # acquire
                  31260, # agricola
                  72125] # "eclipse"

    test_set_2 = [18602, #caylus
                28720, #  brass
                53953] # thunderstone]

    def _worker_thread(games):
        bgg = BoardGameGeek(cache=None, requests_per_minute=20)
        for g in games:
            bgg.game(game_id=g)

    t1 = threading.Thread(target=_worker_thread, args=(test_set_1, ))
    t2 = threading.Thread(target=_worker_thread, args=(test_set_2, ))

    start_time = time.time()
    t1.start()
    t2.start()

    t1.join(timeout=10000)
    t2.join(timeout=10000)
    end_time = time.time()

    # 20 requests per minute => a request every 3 seconds x 6 games => should take around 18 seconds
    assert 15 < end_time - start_time < 21      # +/- a few seconds...


    # second test, use caching and confirm it's working when combined with the rate limiting algorithm
    # do cached requests for the test set, then do them again. should take only half of the time

    bgg = BoardGameGeek(requests_per_minute=20)

    start_time = time.time()
    for g in test_set_1:
        bgg.game(game_id=g)
    end_time = time.time()

    assert 7 < end_time - start_time < 11       # 3 games should take ~9 seconds

    # repeat requests, should be served from cache
    for g in test_set_1:
        bgg.game(game_id=g)

    assert 0 < time.time() - end_time < 2


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    test_rate_limiting_for_requests()
