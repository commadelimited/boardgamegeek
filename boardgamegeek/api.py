# coding: utf-8
"""
:mod:`boardgamegeek.api` - Core functions
=========================================

This module contains the core functionality needed to retrieve data from boardgamegeek.com and parse it into usable
objects.

.. module:: boardgamegeek.api
   :platform: Unix, Windows
   :synopsis: module handling communication with the online BoardGameGeek API

.. moduleauthor:: Cosmin Luță <q4break@gmail.com>
"""
from __future__ import unicode_literals

import logging
import requests
import datetime
import sys
import warnings

# This is required for decoding HTML entities from the description text
# of games
if sys.version_info >= (3,):
    import html.parser as hp
else:
    import HTMLParser as hp


from .games import BoardGame
from .guild import Guild
from .user import User
from .collection import Collection
from .hotitems import HotItems
from .plays import Plays
from .exceptions import BoardGameGeekAPIError, BoardGameGeekError, BoardGameGeekAPIRetryError, BoardGameGeekAPINonXMLError
from .utils import xml_subelement_attr, xml_subelement_text, xml_subelement_attr_list, get_parsed_xml_response
from .utils import fix_unsigned_negative
from .search import SearchResult
from .utils import get_cache_session_from_uri, RateLimitingAdapter, DEFAULT_REQUESTS_PER_MINUTE


log = logging.getLogger("boardgamegeek.api")
html_parser = hp.HTMLParser()

HOT_ITEM_CHOICES = ["boardgame", "rpg", "videogame", "boardgameperson", "rpgperson", "boardgamecompany",
                    "rpgcompany", "videogamecompany"]


class BoardGameGeekNetworkAPI(object):
    """
    Base class for the BoardGameGeek websites APIs. All site-specific clients are derived from this.

    :param str api_endpoint: URL of the API
    :param str cache: URL indicating the cache to use, or ``None`` if caching should be disabled (not recommended)
    :param integer timeout: timeout for a request
    :param integer retries: how many retries to perform in special cases
    :param integer retry_delay: delay between retries (seconds)
    """
    SEARCH_RPG_ITEM = 1
    SEARCH_VIDEO_GAME = 2
    SEARCH_BOARD_GAME = 4
    SEARCH_BOARD_GAME_EXPANSION = 8

    def __init__(self, api_endpoint, cache, timeout, retries, retry_delay, requests_per_minute):
        self._search_api_url = api_endpoint + "/search"
        self._thing_api_url = api_endpoint + "/thing"
        self._guild_api_url = api_endpoint + "/guild"
        self._user_api_url = api_endpoint + "/user"
        self._plays_api_url = api_endpoint + "/plays"
        self._hot_api_url = api_endpoint + "/hot"
        self._collection_api_url = api_endpoint + "/collection"
        self._timeout = timeout
        self._retries = retries
        self._retry_delay = retry_delay

        if cache:
            self.requests_session = get_cache_session_from_uri(cache)
        else:
            self.requests_session = requests.Session()

        # add the rate limiting adapter
        self.requests_session.mount(api_endpoint, RateLimitingAdapter(rpm=requests_per_minute))

    def _get_game_id(self, name, game_type, choose):
        """
        Returns the BGG ID of a game, searching by name

        :param str name: the name of the game to search for
        :param str game_type: the game type ("rpgitem", "videogame", "boardgame", "boardgameexpansion")
        :param str choose: method of selecting the game by name, when dealing with multiple results. Valid values are "first", "recent" or "best-rank"
        :return: ``None`` if game wasn't found
        :return: game's id
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekError` in case of invalid name
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekAPIRetryError` if this request should be retried after a short delay
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekAPIError` if the response couldn't be parsed
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekTimeoutError` if there was a timeout
        """

        if choose not in ["first", "recent", "best-rank"]:
            raise BoardGameGeekError("invalid value for parameter 'choose': {}".format(choose))

        log.debug("getting game id for '{}'".format(name))
        res = self.search(name, search_type=[game_type], exact=True)

        if not res:
            return None

        if choose == "first":
            return res[0].id
        elif choose == "recent":
            return max(res, key=lambda x: x.year if x.year is not None else -300000).id
        else:
            # getting the best rank requires fetching the data of all games returned
            game_data = [self.game(game_id=r.id) for r in res]
            # ...and selecting the one with the best ranking
            return min(game_data, key=lambda x: x.boardgame_rank if x.boardgame_rank is not None else 10000000000).id

    def guild(self, guild_id, progress=None):
        """
        Retrieves details about a guild

        :param integer guild_id: the id number of the guild
        :param callable progress: an optional callable for reporting progress, taking two integers (``current``, ``total``) as arguments
        :return: ``Guild`` object containing the data
        :return: ``None`` if the information couldn't be retrieved
        :rtype: :py:class:`boardgamegeek.guild.Guild`
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekError` in case of an invalid guild id
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekAPIRetryError` if this request should be retried after a short delay
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekAPIError` if the response couldn't be parsed
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekTimeoutError` if there was a timeout
        """

        try:
            guild_id = int(guild_id)
        except:
            raise BoardGameGeekError("invalid guild id")

        try:
            root = get_parsed_xml_response(self.requests_session,
                                           self._guild_api_url,
                                           params={"id": guild_id, "members": 1},
                                           timeout=self._timeout,
                                           retries=self._retries,
                                           retry_delay=self._retry_delay)
        except BoardGameGeekAPINonXMLError:
            return None

        if "name" not in root.attrib:
            log.warn("unable to get guild information (name not found)".format(guild_id))
            return None

        kwargs = {"name": root.attrib["name"],
                  "created": root.attrib.get("created"),
                  "id": guild_id,
                  "members": []}

        # grab initial info from first page
        for tag in ["category", "website", "manager"]:
            kwargs[tag] = xml_subelement_text(root, tag)

        kwargs["description"] = xml_subelement_text(root, "description", convert=html_parser.unescape, quiet=True)

        # Grab location info
        location = root.find("location")
        if location is not None:
            kwargs["city"] = xml_subelement_text(location, "city")
            kwargs["country"] = xml_subelement_text(location, "country")
            kwargs["postalcode"] = xml_subelement_text(location, "postalcode")
            kwargs["addr1"] = xml_subelement_text(location, "addr1")
            kwargs["addr2"] = xml_subelement_text(location, "addr2")
            kwargs["stateorprovince"] = xml_subelement_text(location, "stateorprovince")

        el = root.find(".//members[@count]")
        count = int(el.attrib["count"])

        # first page of members has already been retrieved with the initial call
        for el in root.findall(".//member"):
            kwargs["members"].append(el.attrib["name"])

        def _call_progress_cb():
            if progress is not None:
                progress(len(kwargs["members"]), count)

        _call_progress_cb()

        page = 2

        while len(kwargs["members"]) < count:
            added_member = False
            log.debug("fetching page {}".format(page))
            root = get_parsed_xml_response(self.requests_session,
                                           self._guild_api_url,
                                           params={"id": guild_id, "members": 1, "page": page},
                                           timeout=self._timeout,
                                           retries=self._retries,
                                           retry_delay=self._retry_delay)

            for el in root.findall(".//member"):
                kwargs["members"].append(el.attrib["name"])
                added_member = True

            _call_progress_cb()

            page += 1
            if not added_member:
                # didn't add anything anymore? break
                break

        return Guild(kwargs)

    def user(self, name, progress=None):
        """
        Retrieves details about an user

        :param str name: user's login name
        :param callable progress: an optional callable for reporting progress when fetching the buddy list/guilds, taking two integers (``current``, ``total``) as arguments

        :return: ``User`` object
        :rtype: :py:class:`boardgamegeek.user.User`
        :return: ``None`` if the user couldn't be found

        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekError` in case of invalid user name
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekAPIRetryError` if this request should be retried after a short delay
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekAPIError` if the response couldn't be parsed
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekTimeoutError` if there was a timeout
        """

        if not name:
            raise BoardGameGeekError("no user name specified")

        params = {"name": name, "buddies": 1, "guilds": 1, "hot": 1, "top": 1}

        try:
            root = get_parsed_xml_response(self.requests_session,
                                           self._user_api_url,
                                           params=params,
                                           timeout=self._timeout,
                                           retries=self._retries,
                                           retry_delay=self._retry_delay)
        except BoardGameGeekAPINonXMLError:
            # if the api doesn't return XML, assume the user wasn't found
            return None

        # when the user is not found, the API returns an response, but with most fields empty. id is empty too
        try:
            kwargs = {"name": root.attrib["name"],
                      "id": int(root.attrib["id"])}
        except:
            return None

        for i in ["firstname", "lastname", "avatarlink",
                  "stateorprovince", "country", "webaddress", "xboxaccount",
                  "wiiaccount", "steamaccount", "psnaccount", "traderating"]:
            kwargs[i] = xml_subelement_attr(root, i)

        kwargs["lastlogin"] = xml_subelement_attr(root,
                                                  "lastlogin",
                                                  convert=lambda x: datetime.datetime.strptime(x, "%Y-%m-%d"),
                                                  quiet=True)

        kwargs["yearregistered"] = xml_subelement_attr(root, "yearregistered", convert=int, quiet=True)

        user = User(kwargs)

        # add top items
        for top_item in root.findall(".//top/item"):
            user.add_top_item({"id": int(top_item.attrib["id"]),
                                "name": top_item.attrib["name"]})

        # add hot items
        for hot_item in root.findall(".//hot/item"):
            user.add_hot_item({"id": int(hot_item.attrib["id"]),
                                "name": hot_item.attrib["name"]})

        total_buddies = 0
        total_guilds = 0

        buddies = root.find("buddies")
        if buddies is not None:
            total_buddies = int(buddies.attrib["total"])
            if total_buddies > 0:
                # add the buddies from the first page
                for buddy in buddies.findall(".//buddy"):
                    user.add_buddy({"name": buddy.attrib["name"],
                                    "id": buddy.attrib["id"]})

        guilds = root.find("guilds")
        if guilds is not None:
            total_guilds = int(guilds.attrib["total"])
            if total_guilds > 0:
                # add the guilds from the first page
                for guild in guilds.findall(".//guild"):
                    user.add_guild({"name": guild.attrib["name"],
                                    "id": guild.attrib["id"]})

        # It seems that the BGG API can return more results than what's specified in the documentation (they say
        # page size is 100, but for an user with 114 friends, all buddies are there on the first page).
        # Therefore, we'll keep fetching pages until we reach the number of items we're expecting or we don't get
        # any more data

        max_items_to_fetch = max(total_buddies, total_guilds)

        def _call_progress_cb():
            if progress is not None:
                progress(max(user.total_buddies, user.total_guilds), max_items_to_fetch)

        _call_progress_cb()

        page = 2
        while max(user.total_buddies, user.total_guilds) < max_items_to_fetch:
            added_buddy = False
            added_guild = False
            params["page"] = page
            root = get_parsed_xml_response(self.requests_session,
                                           self._user_api_url,
                                           params=params,
                                           timeout=self._timeout)

            for buddy in root.findall(".//buddy"):
                user.add_buddy({"name": buddy.attrib["name"],
                                "id": buddy.attrib["id"]})
                added_buddy = True

            for guild in root.findall(".//guild"):
                user.add_guild({"name": guild.attrib["name"],
                                "id": guild.attrib["id"]})
                added_guild = True

            _call_progress_cb()
            page += 1

            if not added_buddy and not added_guild:
                log.debug("didn't add any buddy/guild after fetching page {}, stopping here".format(page))
                break

        return user

    def plays(self, name=None, game_id=None, progress=None, min_date=None, max_date=None):
        """
        Retrieves the plays for an user (if using ``name``) or for a game (if using ``game_id``)

        :param str name: user name to retrieve the plays for
        :param integer game_id: game id to retrieve the plays for
        :param callable progress: an optional callable for reporting progress, taking two integers (``current``, ``total``) as arguments
        :param datetime.date min_date: return only plays of the specified date or later.
        :param datetime.date max_date: return only plays of the specified date or earlier.

        :return: object containing all the plays
        :rtype: :py:class:`boardgamegeek.plays.Plays`
        :return: ``None`` if the user/game couldn't be found
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekError` on errors
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekAPIRetryError` if this request should be retried after a short delay
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekAPIError` if the response couldn't be parsed
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekTimeoutError` if there was a timeout

        """
        if not name and not game_id:
            raise BoardGameGeekError("no user name specified")

        if name and game_id:
            raise BoardGameGeekError("can't retrieve by user and by game at the same time")

        if name:
            params = {"username": name}
        else:
            try:
                params = {"id": int(game_id)}
            except:
                raise BoardGameGeekError("invalid game id")

        if min_date:
            try:
                params["mindate"] = min_date.isoformat()
            except AttributeError:
                raise BoardGameGeekError("mindate must be a datetime.date object")

        if max_date:
            try:
                params["maxdate"] = max_date.isoformat()
            except AttributeError:
                raise BoardGameGeekError("maxdate must be a datetime.date object")

        try:
            root = get_parsed_xml_response(self.requests_session,
                                           self._plays_api_url,
                                           params=params,
                                           timeout=self._timeout,
                                           retries=self._retries,
                                           retry_delay=self._retry_delay)
        except BoardGameGeekAPINonXMLError as e:
            # The API seems to return HTML in case of an invalid username.
            # just return None for the time being.
            log.error("error trying to fetch plays: {}".format(e))
            return None

        try:
            # in case of error, the root node doesn't have a 'total' attribute
            count = int(root.attrib["total"])   # how many plays
        except:
            return None

        if name:
            plays = Plays({"username": root.attrib["username"],
                           "user_id": int(root.attrib["userid"])})
        else:
            plays = Plays({"game_id": game_id})

        def _add_plays(plays, root):
            added_plays = False
            for play in root.findall(".//play"):
                added_plays = True

                # if we're listing plays by game, each <play> has an userid. If this isn't set, we must be listing
                # an user's collection, thus set it from plays.user_id
                userid = int(play.attrib.get("userid", plays.user_id))

                player_list = []
                # TODO: add the game subtype too
                kwargs = {"id": int(play.attrib["id"]),
                          "date": play.attrib["date"],
                          "quantity": int(play.attrib["quantity"]),
                          "duration": int(play.attrib["length"]),
                          "incomplete": int(play.attrib["incomplete"]),
                          "nowinstats": int(play.attrib["nowinstats"]),
                          "user_id": userid,
                          "game_id": xml_subelement_attr(play, "item", attribute="objectid", convert=int),
                          "game_name": xml_subelement_attr(play, "item", attribute="name"),
                          "comment": xml_subelement_text(play, "comments"),
                          "players": player_list}

                for player in play.findall(".//player"):
                    player_data = {"username": player.attrib.get("username"),
                                   "user_id": int(player.attrib.get("userid", -1)),
                                   "name": player.attrib.get("name"),
                                   "startposition": player.attrib.get("startposition"),
                                   "new": player.attrib.get("new"),
                                   "win": player.attrib.get("win"),
                                   "rating": player.attrib.get("rating"),
                                   "score": player.attrib.get("score")}

                    player_list.append(player_data)
                plays.add_play(kwargs)

            return added_plays

        _add_plays(plays, root)

        def _call_progress_cb():
            if progress is not None:
                progress(len(plays), count)

        _call_progress_cb()

        page = 2
        while len(plays) < count:
            log.debug("fetching page {} of plays".format(page))

            params["page"] = page

            # fetch the next pages of plays
            root = get_parsed_xml_response(self.requests_session,
                                           self._plays_api_url,
                                           params=params,
                                           timeout=self._timeout,
                                           retries=self._retries,
                                           retry_delay=self._retry_delay)

            if not _add_plays(plays, root):
                break

            page += 1
            _call_progress_cb()

        return plays

    def hot_items(self, item_type):
        """
        Return the list of "Hot Items"

        :param str item_type: hot item type. Valid values: "boardgame", "rpg", "videogame", "boardgameperson", "rpgperson", "boardgamecompany", "rpgcompany", "videogamecompany")

        :return: ``HotItems`` object
        :rtype: :py:class:`boardgamegeek.hotitems.HotItems`
        :return: ``None`` in case the hot items couldn't be retrieved

        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekError` if the parameter is invalid
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekAPIRetryError` if this request should be retried after a short delay
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekAPIError` if the response couldn't be parsed
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekTimeoutError` if there was a timeout
        """
        if item_type not in HOT_ITEM_CHOICES:
            raise BoardGameGeekError("invalid type specified")

        params = {"type": item_type}

        try:
            root = get_parsed_xml_response(self.requests_session,
                                           self._hot_api_url,
                                           params=params,
                                           timeout=self._timeout,
                                           retries=self._retries,
                                           retry_delay=self._retry_delay)
        except BoardGameGeekAPINonXMLError:
            # if the api doesn't return XML, assume there was some error
            return None

        hot_items = HotItems({})

        for item in root.findall("item"):
            kwargs = {"name": xml_subelement_attr(item, "name"),
                      "id": int(item.attrib["id"]),
                      "rank": int(item.attrib["rank"]),
                      "yearpublished": xml_subelement_attr(item, "yearpublished", convert=int, quiet=True),
                      "thumbnail": xml_subelement_attr(item, "thumbnail")}
            hot_items.add_hot_item(kwargs)

        return hot_items

    def collection(self, user_name):
        """
        Returns the user's game collection

        :param str user_name: user name to retrieve the collection for
        :return: ``Collection`` object
        :rtype: :py:class:`boardgamegeek.collection.Collection`
        :return: ``None`` if user not found

        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekError` in case of invalid parameters
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekAPIRetryError` if this request should be retried after a short delay
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekAPIError` if the response couldn't be parsed
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekTimeoutError` if there was a timeout
        """
        if not user_name:
            raise BoardGameGeekError("no user name specified")

        try:
            root = get_parsed_xml_response(self.requests_session,
                                           self._collection_api_url,
                                           params={"username": user_name, "stats": 1},
                                           timeout=self._timeout,
                                           retries=self._retries,
                                           retry_delay=self._retry_delay)
        except BoardGameGeekAPINonXMLError:
            return None

        # check if there's an error (e.g. invalid username)
        error = root.find(".//error")
        if error is not None:
            message = xml_subelement_text(error, "message")
            log.error("error fetching collection for {}: {}".format(user_name, message))
            return None

        collection = Collection({"owner": user_name, "items": []})

        # search for all boardgames in the collection, add them to the list
        for xml_el in root.findall(".//item[@subtype='boardgame']"):
            # get the user's rating for this game in his collection
            stats = xml_el.find("stats")
            rating = xml_subelement_attr(stats, "rating", convert=float, quiet=True)

            # name and id of the game in collection
            game = {"name": xml_subelement_text(xml_el, "name"),
                    "id": int(xml_el.attrib.get("objectid")),
                    "rating": rating}

            status = xml_el.find("status")
            game.update({stat: status.attrib.get(stat) for stat in ["lastmodified",
                                                                    "own",
                                                                    "preordered",
                                                                    "prevowned",
                                                                    "want",
                                                                    "wanttobuy",
                                                                    "wanttoplay",
                                                                    "fortrade",
                                                                    "wishlist",
                                                                    "wishlistpriority"]})

            collection.add_game(game)

        return collection

    def search(self, query, search_type=None, exact=False):
        """
        Search for a game

        :param str query: the string to search for
        :param str search_type: list of strings indicating what to search for. Valid contained values are: "rpgitem", "videogame", "boardgame" (default), "boardgameexpansion"
        :param bool exact: if True, try to match the name exactly
        :return: list of ``SearchResult``
        :rtype: list of :py:class:`boardgamegeek.search.SearchResult`

        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekError` in case of invalid query
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekAPIRetryError` if this request should be retried after a short delay
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekAPIError` if the response couldn't be parsed
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekTimeoutError` if there was a timeout
        """
        if not query:
            raise BoardGameGeekError("invalid query string")

        if search_type is None:
            search_type = ["boardgame"]

        params = {"query": query}

        if type(search_type) != list:
            warnings.warn("numeric values for the `search_type` parameter will no longer be supported in future versions. See the documentation for details",
                          UserWarning)

            s_type = []

            if search_type:
                if search_type & BoardGameGeekNetworkAPI.SEARCH_BOARD_GAME:
                    s_type.append("boardgame")
                if search_type & BoardGameGeekNetworkAPI.SEARCH_BOARD_GAME_EXPANSION:
                    s_type.append("boardgameexpansion")
                if search_type & BoardGameGeekNetworkAPI.SEARCH_RPG_ITEM:
                    s_type.append("rpgitem")
                if search_type & BoardGameGeekNetworkAPI.SEARCH_VIDEO_GAME:
                    s_type.append("videogame")

            if s_type:
                params["type"] = ",".join(s_type)
        else:
            if search_type:
                for s in search_type:
                    if s not in ["rpgitem", "videogame", "boardgame", "boardgameexpansion"]:
                        raise BoardGameGeekError("invalid search type: {}".format(search_type))

                params["type"] = ",".join(search_type)

        if exact:
            params["exact"] = 1

        try:
            root = get_parsed_xml_response(self.requests_session,
                                           self._search_api_url,
                                           params=params,
                                           timeout=self._timeout,
                                           retries=self._retries,
                                           retry_delay=self._retry_delay)
        except BoardGameGeekAPINonXMLError:
            # if the api doesn't return XML, assume there was some error
            return None

        results = []
        for item in root.findall("item"):
            kwargs = {"id": item.attrib["id"],
                      "name": xml_subelement_attr(item, "name"),
                      "yearpublished": fix_unsigned_negative(xml_subelement_attr(item,
                                                                                 "yearpublished",
                                                                                 default=0,
                                                                                 convert=int,
                                                                                 quiet=True)),
                      "type": item.attrib["type"]}

            results.append(SearchResult(kwargs))

        return results


class BoardGameGeek(BoardGameGeekNetworkAPI):
    """
        Python interface for www.boardgamegeek.com's XML API 2.

        Caching for the requests can be used by specifying an URI for the ``cache`` parameter. By default, an in-memory
        cache is used, with sqlite being the other currently supported option.

        :param cache: URL indicating the cache to use for HTTP requests, ``None`` if disabled
        :param timeout: Timeout for network operations
        :param retries: Number of retries to perform in case the API returns HTTP 202 (retry) or in case of timeouts
        :param retry_delay: Time to sleep between retries when the API returns HTTP 202 (retry)
        :param disable_ssl: If true, use HTTP instead of HTTPS for calling the BGG API
        :param requests_per_minute: how many requests per minute to allow to go out to BGG (throttle prevention)

        Example usage::

            >>> bgg = BoardGameGeek()
            >>> game = bgg.game("Android: Netrunner")
            >>> game.id
            124742
            >>> bgg_no_cache = BoardGameGeek(cache=None)
            >>> bgg_sqlite_cache = BoardGameGeek(cache="sqlite:///path/to/cache.db?ttl=3600")

    """
    def __init__(self, cache="memory:///?ttl=3600", timeout=15, retries=3, retry_delay=5, disable_ssl=False, requests_per_minute=DEFAULT_REQUESTS_PER_MINUTE):

        api_endpoint = "http{}://www.boardgamegeek.com/xmlapi2".format("" if disable_ssl else "s")
        super(BoardGameGeek, self).__init__(api_endpoint=api_endpoint,
                                            cache=cache,
                                            timeout=timeout,
                                            retries=retries,
                                            retry_delay=retry_delay,
                                            requests_per_minute=requests_per_minute)

    def get_game_id(self, name, choose="first"):
        """
        Returns the BGG ID of a game, searching by name

        :param str name: The name of the game to search for
        :param str choose: method of selecting the game by name, when dealing with multiple results. Valid values are "first", "recent" or "best-rank"
        :return: the game's id
        :rtype: integer
        :return: ``None`` if game wasn't found
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekError` in case of invalid name
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekAPIRetryError` if this request should be retried after a short delay
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekAPIError` if the response couldn't be parsed
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekTimeoutError` if there was a timeout
        """
        return self._get_game_id(name, game_type="boardgame", choose=choose)

    def game(self, name=None, game_id=None, choose="first"):
        """
        Get information about a game.

        :param str name: If not None, get information about a game with this name
        :param integer game_id:  If not None, get information about a game with this id
        :param str choose: method of selecting the game by name, when dealing with multiple results. Valid values are "first", "recent" or "best-rank"
        :return: ``BoardGame`` object
        :rtype: :py:class:`boardgamegeek.games.BoardGame`
        :return: ``None`` if the game wasn't found

        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekError` in case of invalid name or game_id
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekAPIRetryError` if this request should be retried after a short delay
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekAPIError` if the response couldn't be parsed
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekTimeoutError` if there was a timeout
        """

        if not name and game_id is None:
            raise BoardGameGeekError("game name or id not specified")

        if game_id is None:
            game_id = self.get_game_id(name, choose=choose)
            if game_id is None:
                log.error("couldn't find any game named '{}'".format(name))
                return None

        log.debug("retrieving game id {}{}".format(game_id, " ({})".format(name) if name is not None else ""))

        try:
            root = get_parsed_xml_response(self.requests_session,
                                           self._thing_api_url,
                                           params={"id": game_id, "stats": 1},
                                           timeout=self._timeout,
                                           retries=self._retries,
                                           retry_delay=self._retry_delay)
        except BoardGameGeekAPINonXMLError:
            return None

        # xml is structured like <item ...> blablabla><item>..
        root = root.find("item")
        if root is None:
            msg = "error parsing game data for game id: {}{}".format(game_id,
                                                                      " ({})".format(name) if name is not None else "")
            raise BoardGameGeekAPIError(msg)

        game_type = root.attrib["type"]
        if game_type not in ["boardgame", "boardgameexpansion"]:
            log.debug("item id {} is not a boardgame (type: {})".format(game_id, game_type))
            raise BoardGameGeekError("item is not a board game")

        kwargs = {"id": game_id,
                  "thumbnail": xml_subelement_text(root, "thumbnail"),
                  "image": xml_subelement_text(root, "image"),
                  "expansion": game_type == "boardgameexpansion",       # is this game an expansion?
                  "families": xml_subelement_attr_list(root, ".//link[@type='boardgamefamily']"),
                  "categories": xml_subelement_attr_list(root, ".//link[@type='boardgamecategory']"),
                  "implementations": xml_subelement_attr_list(root, ".//link[@type='boardgameimplementation']"),
                  "mechanics": xml_subelement_attr_list(root, ".//link[@type='boardgamemechanic']"),
                  "designers": xml_subelement_attr_list(root, ".//link[@type='boardgamedesigner']"),
                  "artists": xml_subelement_attr_list(root, ".//link[@type='boardgameartist']"),
                  "publishers": xml_subelement_attr_list(root, ".//link[@type='boardgamepublisher']")}

        expands = []        # list of items this game expands
        expansions = []     # list of expansions this game has
        for e in root.findall(".//link[@type='boardgameexpansion']"):
            item = {"id": e.attrib["id"],
                    "name": e.attrib["value"]}

            if e.attrib.get("inbound", "false").lower()[0] == 't':
                # this is an item expanded by game_id
                expands.append(item)
            else:
                expansions.append(item)

        kwargs["expansions"] = expansions
        kwargs["expands"] = expands
        kwargs["description"] = xml_subelement_text(root, "description", convert=html_parser.unescape, quiet=True)

        # These XML elements have a numberic value, attempt to convert them to integers
        for i in ["yearpublished", "minplayers", "maxplayers", "playingtime", "minage", "minplaytime", "maxplaytime"]:
            kwargs[i] = xml_subelement_attr(root, i, convert=int, quiet=True)

        # What's the name of the game :P
        kwargs["name"] = xml_subelement_attr(root, ".//name[@type='primary']")

        # Get alternative names too
        kwargs["alternative_names"] = xml_subelement_attr_list(root, ".//name[@type='alternate']")

        # look for statistics info
        stats = root.find(".//ratings")
        kwargs.update({
            "usersrated": xml_subelement_attr(stats, "usersrated", convert=int, quiet=True),
            "average": xml_subelement_attr(stats, "average", convert=float, quiet=True),
            "bayesaverage": xml_subelement_attr(stats, "bayesaverage", convert=float, quiet=True),
            "stddev": xml_subelement_attr(stats, "stddev", convert=float, quiet=True),
            "median": xml_subelement_attr(stats, "median", convert=float, quiet=True),
            "owned": xml_subelement_attr(stats, "owned", convert=int, quiet=True),
            "trading": xml_subelement_attr(stats, "trading", convert=int, quiet=True),
            "wanting": xml_subelement_attr(stats, "wanting", convert=int, quiet=True),
            "wishing": xml_subelement_attr(stats, "wishing", convert=int, quiet=True),
            "numcomments": xml_subelement_attr(stats, "numcomments", convert=int, quiet=True),
            "numweights": xml_subelement_attr(stats, "numweights", convert=int, quiet=True),
            "averageweight": xml_subelement_attr(stats, "averageweight", convert=float, quiet=True)
        })

        kwargs["ranks"] = []
        ranks = root.findall(".//rank")
        for rank in ranks:
            try:
                rank_value = int(rank.attrib.get("value"))
            except:
                rank_value = None
            kwargs["ranks"].append({"name": rank.attrib.get("name"),
                                    "friendlyname": rank.attrib.get("friendlyname"),
                                    "value": rank_value})

        return BoardGame(kwargs)

    def games(self, name):
        """
        Return a list containing all games with the given name

        :param str name: the name of the game to search for
        :return: list of :py:class:`boardgamegeek.games.BoardGame`
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekAPIRetryError` if this request should be retried after a short delay
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekAPIError` if the response couldn't be parsed
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekTimeoutError` if there was a timeout
        """
        return [self.game(game_id=s.id)
                for s in self.search(name,
                                     search_type=["boardgame", "boardgameexpansion"],
                                     exact=True)]
