# coding: utf-8
"""
:mod:`boardgamegeek.games` - Games information
==============================================

.. module:: boardgamegeek.games
   :platform: Unix, Windows
   :synopsis: classes for storing games information

.. moduleauthor:: Cosmin Luță <q4break@gmail.com>

"""
from __future__ import unicode_literals
from copy import copy

from .things import Thing
from .exceptions import BoardGameGeekError
from .utils import fix_url


class CollectionBoardGame(Thing):
    """
    A boardgame retrieved from the collection information, which has less information than the one retrieved
    via the /thing api and which also contains some user-specific information.
    """
    def __repr__(self):
        return "CollectionBoardGame (id: {})".format(self.id)

    def _format(self, log):
        log.info("boardgame id      : {}".format(self.id))
        log.info("boardgame name    : {}".format(self.name))

        log.info("last modified     : {}".format(self.lastmodified))

        log.info("rating            : {}".format(self.rating))
        log.info("own               : {}".format(self.owned))
        log.info("preordered        : {}".format(self.preordered))
        log.info("previously owned  : {}".format(self.prev_owned))
        log.info("want              : {}".format(self.want))
        log.info("want to buy       : {}".format(self.want_to_buy))
        log.info("want to play      : {}".format(self.want_to_play))
        log.info("wishlist          : {}".format(self.wishlist))
        log.info("wishlist priority : {}".format(self.wishlist_priority))
        log.info("for trade         : {}".format(self.for_trade))

    @property
    def lastmodified(self):
        return self._data.get("lastmodified")

    @property
    def last_modified(self):
        """
        :return: last modified date
        :rtype: str
        """
        return self._data.get("lastmodified")

    @property
    def rating(self):
        """
        :return: game rating
        :rtype: float
        :return: ``None`` if n/a
        """
        return self._data.get("rating")

    @property
    def owned(self):
        """
        :return: game owned
        :rtype: bool
        """
        return bool(int(self._data.get("own", 0)))

    @property
    def preordered(self):
        """
        :return: game preordered
        :rtype: bool
        """
        return bool(int(self._data.get("preordered", 0)))

    @property
    def prev_owned(self):
        """
        :return: game previously owned
        :rtype: bool
        """
        return bool(int(self._data.get("prevowned", 0)))

    @property
    def want(self):
        """
        :return: game wanted
        :rtype: bool
        """
        return bool(int(self._data.get("want", 0)))

    @property
    def want_to_buy(self):
        """
        :return: want to buy
        :rtype: bool
        """
        return bool(int(self._data.get("wanttobuy", 0)))

    @property
    def want_to_play(self):
        """
        :return: want to play
        :rtype: bool
        """
        return bool(int(self._data.get("wanttoplay", 0)))

    @property
    def for_trade(self):
        """
        :return: game for trading
        :rtype: bool
        """
        return bool(int(self._data.get("fortrade", 0)))

    @property
    def wishlist(self):
        """
        :return: game on wishlist
        :rtype: bool
        """
        return bool(int(self._data.get("wishlist", 0)))

    @property
    def wishlist_priority(self):
        # TODO: convert to int (it's str)
        return self._data.get("wishlistpriority")


class BoardGame(Thing):
    """
    Object containing information about a boardgame
    """
    def __init__(self, data):

        kw = copy(data)

        # if we have any "expansions" for this item..
        if "expansions" not in kw:
            kw["expansions"] = []

        for to_fix in ["thumbnail", "image"]:
            if to_fix in kw:
                kw[to_fix] = fix_url(kw[to_fix])

        self._expansions = []           # list of Thing for the expansions
        self._expansions_set = set()    # set for making sure things are unique
        for data in kw["expansions"]:
            try:
                if data["id"] not in self._expansions_set:
                    self._expansions_set.add(data["id"])
                    self._expansions.append(Thing(data))
            except KeyError:
                raise BoardGameGeekError("invalid expansion data")

        # if this item expands something...
        if "expands" not in kw:
            kw["expands"] = []

        self._expands = []              # list of Thing which this item expands
        self._expands_set = set()       # set for keeping things unique
        for data in kw["expands"]:         # for all the items this game expands, create a Thing
            try:
                if data["id"] not in self._expands_set:
                    self._expands_set.add(data["id"])
                    self._expands.append(Thing(data))
            except KeyError:
                raise BoardGameGeekError("invalid expanded game data")

        self.boardgame_rank = None

        if "ranks" in kw:
            # try to search for the boardgame rank of this game
            for rank in kw["ranks"]:
                if rank.get("name") == "boardgame":
                    value = rank.get("value")
                    if value is None:
                        self.boardgame_rank = None
                    else:
                        self.boardgame_rank = int(value)
                    break

        super(BoardGame, self).__init__(kw)

    def __repr__(self):
        return "BoardGame (id: {})".format(self.id)

    def add_expanded_game(self, data):
        """
        Add a game expanded by this one

        :param dict data: expanded game's data
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekError` if data is invalid
        """
        try:
            if data["id"] not in self._expands_set:
                self._data["expands"].append(data)
                self._expands_set.add(data["id"])
                self._expands.append(Thing(data))
        except KeyError:
            raise BoardGameGeekError("invalid expanded game data")

    def add_expansion(self, data):
        """
        Add an expansion of this game

        :param dict data: expansion data
        :raises: :py:exc:`boardgamegeek.exceptions.BoardGameGeekError` if data is invalid
        """
        try:
            if data["id"] not in self._expansions_set:
                self._data["expansions"].append(data)
                self._expansions_set.add(data["id"])
                self._expansions.append(Thing(data))
        except KeyError:
            raise BoardGameGeekError("invalid expansion data")

    def _format(self, log):
        log.info("boardgame id      : {}".format(self.id))
        log.info("boardgame name    : {}".format(self.name))
        log.info("boardgame rank    : {}".format(self.boardgame_rank))
        if self.alternative_names:
            for i in self.alternative_names:
                log.info("alternative name  : {}".format(i))
        log.info("year published    : {}".format(self.year))
        log.info("minimum players   : {}".format(self.min_players))
        log.info("maximum players   : {}".format(self.max_players))
        log.info("playing time      : {}".format(self.playing_time))
        log.info("minimum play time : {}".format(self.min_playing_time))
        log.info("maximum play time : {}".format(self.max_playing_time))
        log.info("minimum age       : {}".format(self.min_age))
        log.info("thumbnail         : {}".format(self.thumbnail))
        log.info("image             : {}".format(self.image))

        log.info("is expansion      : {}".format(self.expansion))

        if self.expansions:
            log.info("expansions")
            for i in self.expansions:
                log.info("- {}".format(i.name))

        if self.expands:
            log.info("expands")
            for i in self.expands:
                log.info("- {}".format(i.name))

        if self.categories:
            log.info("categories")
            for i in self.categories:
                log.info("- {}".format(i))

        if self.families:
            log.info("families")
            for i in self.families:
                log.info("- {}".format(i))

        if self.mechanics:
            log.info("mechanics")
            for i in self.mechanics:
                log.info("- {}".format(i))

        if self.implementations:
            log.info("implementations")
            for i in self.implementations:
                log.info("- {}".format(i))

        if self.designers:
            log.info("designers")
            for i in self.designers:
                log.info("- {}".format(i))

        if self.artists:
            log.info("artistis")
            for i in self.artists:
                log.info("- {}".format(i))

        if self.publishers:
            log.info("publishers")
            for i in self.publishers:
                log.info("- {}".format(i))

        log.info("users rated game  : {}".format(self.users_rated))
        log.info("users avg rating  : {}".format(self.rating_average))
        log.info("users b-avg rating: {}".format(self.rating_bayes_average))
        log.info("users commented   : {}".format(self.users_commented))
        log.info("users owned       : {}".format(self.users_owned))
        log.info("users wanting     : {}".format(self.users_wanting))
        log.info("users wishing     : {}".format(self.users_wishing))
        log.info("users trading     : {}".format(self.users_trading))
        log.info("ranks             : {}".format(self.ranks))
        log.info("description       : {}".format(self.description))

    @property
    def alternative_names(self):
        """
        :return: alternative names
        :rtype: list of str
        """
        return self._data.get("alternative_names", [])

    @property
    def thumbnail(self):
        """
        :return: thumbnail URL
        :rtype: str
        :return: ``None`` if n/a
        """
        return self._data.get("thumbnail")

    @property
    def image(self):
        """
        :return: image URL
        :rtype: str
        :return: ``None`` if n/a
        """
        return self._data.get("image")

    @property
    def description(self):
        """
        :return: description
        :rtype: str
        """
        return self._data.get("description", "")

    @property
    def families(self):
        """
        :return: families
        :rtype: list of str
        """
        return self._data.get("families", [])

    @property
    def categories(self):
        """
        :return: categories
        :rtype: list of str
        """
        return self._data.get("categories", [])

    @property
    def mechanics(self):
        """
        :return: mechanics
        :rtype: list of str
        """
        return self._data.get("mechanics", [])

    @property
    def expansions(self):
        """
        :return: expansions
        :rtype: list of :py:class:`boardgamegeek.things.Thing`
        """
        return self._expansions

    @property
    def expands(self):
        """
        :return: games this item expands
        :rtype: list of :py:class:`boardgamegeek.things.Thing`
        """
        return self._expands

    @property
    def implementations(self):
        """
        :return: implementations
        :rtype: list of str
        """
        return self._data.get("implementations", [])

    @property
    def designers(self):
        """
        :return: designers
        :rtype: list of str
        """
        return self._data.get("designers", [])

    @property
    def artists(self):
        """
        :return: artists
        :rtype: list of str
        """
        return self._data.get("artists", [])

    @property
    def publishers(self):
        """
        :return: publishers
        :rtype: list of str
        """
        return self._data.get("publishers", [])

    @property
    def expansion(self):
        """
        :return: True if this item is an expansion
        :rtype: bool
        """
        return self._data.get("expansion", False)

    @property
    def year(self):
        """
        :return: publishing year
        :rtype: integer
        :return: ``None`` if n/a
        """
        return self._data.get("yearpublished")

    @property
    def min_players(self):
        """
        :return: minimum number of players
        :rtype: integer
        :return: ``None`` if n/a
        """
        return self._data.get("minplayers")

    @property
    def max_players(self):
        """
        :return: maximum number of players
        :rtype: integer
        :return: ``None`` if n/a
        """
        return self._data.get("maxplayers")

    @property
    def playing_time(self):
        """
        :return: playing time
        :rtype: integer
        :return: ``None`` if n/a
        """
        return self._data.get("playingtime")

    @property
    def min_playing_time(self):
        """
        :return: minimum playing time
        :rtype: integer
        :return: ``None`` if n/a
        """
        return self._data.get("minplaytime")

    @property
    def max_playing_time(self):
        """
        :return: maximum playing time
        :rtype: integer
        :return: ``None`` if n/a
        """
        return self._data.get("maxplaytime")

    @property
    def min_age(self):
        """
        :return: minimum recommended age
        :rtype: integer
        :return: ``None`` if n/a
        """
        return self._data.get("minage")

    @property
    def users_rated(self):
        """
        :return: how many users rated the game
        :rtype: integer
        :return: ``None`` if n/a
        """
        return self._data.get("usersrated")

    @property
    def rating_average(self):
        """
        :return: average rating
        :rtype: float
        :return: ``None`` if n/a
        """
        return self._data.get("average")

    @property
    def rating_bayes_average(self):
        """
        :return: bayes average rating
        :rtype: float
        :return: ``None`` if n/a
        """
        return self._data.get("bayesaverage")

    @property
    def rating_stddev(self):
        """
        :return: standard deviation
        :rtype: float
        :return: ``None`` if n/a
        """
        return self._data.get("stddev")

    @property
    def rating_median(self):
        """
        :return:
        :rtype: float
        :return: ``None`` if n/a
        """
        return self._data.get("median")

    @property
    def users_owned(self):
        """
        :return: number of users owning this game
        :rtype: integer
        :return: ``None`` if n/a
        """
        return self._data.get("owned")

    @property
    def users_trading(self):
        """
        :return: number of users trading this game
        :rtype: integer
        :return: ``None`` if n/a
        """
        return self._data.get("trading")

    @property
    def users_wanting(self):
        """
        :return: number of users wanting this game
        :rtype: integer
        :return: ``None`` if n/a
        """
        return self._data.get("wanting")

    @property
    def users_wishing(self):
        """
        :return: number of users wishing for this game
        :rtype: integer
        :return: ``None`` if n/a
        """
        return self._data.get("wishing")

    @property
    def users_commented(self):
        """
        :return: number of user comments
        :rtype: integer
        :return: ``None`` if n/a
        """
        return self._data.get("numcomments")

    @property
    def rating_num_weights(self):
        """
        :return:
        :rtype: integer
        :return: ``None`` if n/a
        """
        return self._data.get("numweights")

    @property
    def rating_average_weight(self):
        """
        :return: average weight
        :rtype: float
        :return: ``None`` if n/a
        """
        return self._data.get("averageweight")

    @property
    def ranks(self):
        """
        :return: rankings of this game
        :rtype: list of dicts, keys: ``friendlyname`` (the friendly name of the rank, e.g. "Board Game Rank"), ``name``
                (name of the rank, e.g "boardgame"), ``value`` (the rank)
        :return: ``None`` if n/a
        """
        return self._data.get("ranks")
