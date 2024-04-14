import base64
import datetime
import inspect
import io
import json
import PIL.Image
import re
import traceback
import types
import typing
import urllib.parse

from . import constants
from . import exceptions
from . import helpers

from voussoirkit import expressionmatch
from voussoirkit import imagetools
from voussoirkit import pathclass
from voussoirkit import sentinel
from voussoirkit import sqlhelpers
from voussoirkit import stringtools
from voussoirkit import vlogging
from voussoirkit import worms

log = vlogging.get_logger(__name__)

class ObjectBase(worms.Object):
    def __init__(self, bringdb):
        super().__init__(bringdb)
        self.bringdb = bringdb
        # To be lazily retrieved by @property author.
        self._author = None

class Feed(ObjectBase):
    table = 'feeds'
    no_such_exception = exceptions.NoSuchFeed

    def __init__(self, bringdb, db_row):
        super().__init__(bringdb)

        self.id = db_row['id']
        self.parent_id = db_row['parent_id']
        self.rss_url = db_row['rss_url']
        self.web_url = db_row['web_url']
        self.title = db_row['title']
        self.description = db_row['description']
        self.created = db_row['created']
        self.refresh_with_others = db_row['refresh_with_others']
        self.last_refresh = db_row['last_refresh']
        self.last_refresh_attempt = db_row['last_refresh_attempt']
        self.last_refresh_error = db_row['last_refresh_error']
        self.autorefresh_interval = db_row['autorefresh_interval']
        if db_row['http_headers']:
            self.http_headers = json.loads(db_row['http_headers'])
        else:
            self.http_headers = {}
        self.isolate_guids = db_row['isolate_guids']
        self.icon = db_row['icon']
        self.ui_order_rank = db_row['ui_order_rank']

        self._parent = None

    def __repr__(self):
        if self.title:
            return f'Feed:{self.id}:{self.title}'
        else:
            return f'Feed:{self.id}'

    @staticmethod
    def normalize_autorefresh_interval(autorefresh_interval):
        if isinstance(autorefresh_interval, float):
            autorefresh_interval = int(autorefresh_interval)

        if not isinstance(autorefresh_interval, int):
            raise TypeError(autorefresh_interval)

        return autorefresh_interval

    normalize_description = helpers.normalize_string_blank_to_none

    @staticmethod
    def normalize_http_headers(http_headers):
        if http_headers is None:
            return {}

        if isinstance(http_headers, dict):
            for (key, value) in http_headers.items():
                if not isinstance(key, str):
                    raise TypeError(key)
                if not isinstance(value, str):
                    raise TypeError(value)
            return http_headers

        if isinstance(http_headers, str):
            lines = http_headers.splitlines()
            lines = [line.strip() for line in lines]
            lines = [line for line in lines if line]
            http_headers = {}
            for line in lines:
                if ':' not in line:
                    raise exceptions.InvalidHTTPHeaders(f'"{line}" does not have a key:value pair.')
                (key, value) = line.split(':', 1)
                http_headers[key.strip()] = value.strip()
            return http_headers

        raise TypeError(http_headers)

    @staticmethod
    def normalize_http_headers_json(http_headers):
        http_headers = Feed.normalize_http_headers(http_headers)
        if len(http_headers) == 0:
            return None
        return json.dumps(http_headers)

    @staticmethod
    def normalize_icon(icon:typing.Union[bytes, PIL.Image.Image]) -> bytes:
        if icon is None:
            return None

        if isinstance(icon, bytes):
            icon = PIL.Image.open(io.BytesIO(icon))

        if not isinstance(icon, PIL.Image.Image):
            raise TypeError(icon)

        icon = icon.convert('RGBA')
        (new_w, new_h) = imagetools.fit_into_bounds(
            image_width=icon.size[0],
            image_height=icon.size[1],
            frame_width=32,
            frame_height=32,
            only_shrink=True,
        )
        icon = icon.resize((new_w, new_h), PIL.Image.LANCZOS)
        bio = io.BytesIO()
        icon.save(bio, format='png')
        bio.seek(0)
        icon = bio.read()
        return icon

    @staticmethod
    def normalize_isolate_guids(isolate_guids):
        if not isinstance(isolate_guids, bool):
            raise TypeError(isolate_guids)

        return isolate_guids

    @staticmethod
    def normalize_refresh_with_others(refresh_with_others):
        if not isinstance(refresh_with_others, bool):
            raise TypeError(refresh_with_others)

        return refresh_with_others

    normalize_rss_url = helpers.normalize_string_blank_to_none

    normalize_title = helpers.normalize_string_blank_to_none

    @staticmethod
    def normalize_ui_order_rank(ui_order_rank):
        # The user can provide a float to squeeze between two numbers, then the
        # automatic reassignment will re-count them back into ints.
        if not isinstance(ui_order_rank, (int, float)):
            raise TypeError(ui_order_rank)

        if ui_order_rank <= 0:
            raise ValueError(ui_order_rank)

        return ui_order_rank

    normalize_web_url = helpers.normalize_string_blank_to_none

    @worms.atomic
    def clear_last_refresh_error(self):
        if self.last_refresh_error is None:
            return

        pairs = {
            'id': self.id,
            'last_refresh_error': None,
        }
        self.bringdb.update(table=Feed, pairs=pairs, where_key='id')
        self.last_refresh_error = None

    @worms.atomic
    def delete(self):
        self.assert_not_deleted()

        using_filters = []
        for filt in self.bringdb.get_filters():
            match = re.search(rf'move_to_feed\s*:\s*{self.id}', filt._actions)
            if match:
                using_filters.append(filt)

        if using_filters:
            raise exceptions.FeedStillInUse(feed=self, filters=using_filters)

        # No turning back
        log.info('Deleting %s.', self)
        for child in list(self.get_children()):
            child.set_parent(self.parent)
        self.set_filters([])
        self.bringdb.delete(table=News, pairs={'feed_id': self.id})
        self.bringdb.delete(table=Feed, pairs={'id': self.id})
        self.deleted = True

    @property
    def display_name(self):
        if self.title:
            return self.title
        elif self.rss_url:
            return self.rss_url
        else:
            return str(self.id)

    def get_children(self):
        query = 'SELECT * FROM feeds WHERE parent_id == ? ORDER BY ui_order_rank ASC'
        bindings = [self.id]
        return self.bringdb.get_feeds_by_sql(query, bindings)

    def get_filters(self):
        query = 'SELECT filter_id FROM feed_filter_rel WHERE feed_id == ? ORDER BY order_rank ASC'
        bindings = [self.id]
        filter_ids = self.bringdb.select_column(query, bindings)
        return [self.bringdb.get_filter(id) for id in filter_ids]

    def get_unread_count(self):
        feed_ids = sqlhelpers.listify(descendant.id for descendant in self.walk_children())
        query = f'SELECT COUNT(id) FROM news WHERE recycled == 0 AND read == 0 AND feed_id IN {feed_ids}'
        return self.bringdb.select_one(query)[0]

    def is_ancestor(self, other):
        return any(self == ancestor for ancestor in other.walk_parents())

    def is_descendant(self, other):
        return other.is_ancestor(self)

    def jsonify(
            self,
            *,
            complete=False,
            filters=False,
            icon=False,
            unread_count=False,
        ) -> dict:
        self.assert_not_deleted()
        j = {
            'type': 'feed',
            'id': self.id,
            'autorefresh_interval': self.autorefresh_interval,
            'created': self.created,
            'description': self.description,
            'display_name': self.display_name,
            'http_headers': self.http_headers,
            'isolate_guids': self.isolate_guids,
            'last_refresh': self.last_refresh,
            'last_refresh_attempt': self.last_refresh_attempt,
            'last_refresh_error': self.last_refresh_error,
            'parent_id': self.parent_id,
            'rss_url': self.rss_url,
            'title': self.title,
            'ui_order_rank': self.ui_order_rank,
            'web_url': self.web_url,
        }
        if complete or filters:
            j['filters'] = [filt.jsonify() for filt in self.get_filters()]

        if complete or icon:
            if self.icon:
                icon = base64.b64encode(self.icon).decode('ascii')
            else:
                icon = None
            j['icon'] = icon

        if complete or unread_count:
            j['unread_count'] = self.get_unread_count()

        return j

    @property
    def next_refresh(self) -> float:
        '''
        Return the timestamp of the next time this feed should be refreshed.
        Should be compared against the value that comes out of
        bringrss.helpers.now().

        Returns infinity if this feed is not suitable for refreshing (a folder
        with no RSS url of its own) or has autorefresh disabled. This way you
        can do `if now > feed.next_refresh` for all feeds.
        '''
        if not self.rss_url:
            return float('inf')

        if self.autorefresh_interval < 1:
            return float('inf')

        # Consideration: we could add special logic so that if the previous
        # attempt failed, we don't wait the full interval to try again. For
        # example, a feed you refresh every day could suddenly become two days
        # late just because of a temporary 503 issue. We could make it so that
        # there is a short initial retry at an hour or so, then exponential
        # backoff until reaching the regularly scheduled interval. But this will
        # require persisting the number of failures in a row and I don't want to
        # pollute the db scheme with stuff like this. Perhaps it could be an
        # in-memory only attribute on the assumption that the daemon is
        # long-running anyway, to the detriment of cronjob based refreshes.

        return self.last_refresh_attempt + self.autorefresh_interval

    @property
    def parent(self):
        if self.parent_id is None:
            return None

        if self._parent is None:
            self._parent = self.bringdb.get_feed(self.parent_id)

        return self._parent

    def _refresh_feed_properties_atom(self, soup):
        feed = soup.find('feed')

        if not feed:
            raise ValueError('No feed element!')

        if not self.title:
            title = feed.find('title')
            if title is not None:
                title = title.text.strip()
                if title:
                    self.set_title(title)

        if not self.description:
            description = feed.find('subtitle')
            if description is not None:
                description = description.text.strip()
                if description:
                    self.set_description(description)

        if not self.web_url:
            web_url = helpers.pick_web_url_atom(feed)
            if web_url != self.web_url:
                self.set_web_url(web_url)

    def _refresh_feed_properties_rss(self, soup):
        rss = soup.find('rss')

        if not rss:
            raise ValueError('No rss element!')

        channel = rss.find('channel')

        if not channel:
            raise ValueError('No channel element!')

        if not self.title:
            title = channel.find('title')
            if title is not None:
                title = title.text.strip()
                if title:
                    self.set_title(title)

        if not self.description:
            description = channel.find('description')
            if description is not None:
                description = description.text.strip()
                if description:
                    self.set_description(description)

        if not self.web_url:
            web_url = channel.find('link')
            if web_url is not None:
                web_url = web_url.text.strip()
                if web_url:
                    self.set_web_url(web_url)

    @worms.atomic
    def _refresh(self):
        soup = helpers.fetch_xml_cached(self.rss_url, headers=self.http_headers)

        if helpers.xml_is_atom(soup):
            self._refresh_feed_properties_atom(soup)
        elif helpers.xml_is_rss(soup):
            self._refresh_feed_properties_rss(soup)
        else:
            raise exceptions.NeitherAtomNorRSS(self.rss_url)

        if not self.icon:
            self._set_icon_by_domain_favicon()

        self.bringdb.ingest_news_xml(soup, feed=self)
        self.last_refresh = int(helpers.now())
        pairs = {
            'id': self.id,
            'last_refresh': self.last_refresh,
        }
        self.bringdb.update(table=Feed, pairs=pairs, where_key='id')

    @worms.atomic
    def refresh(self):
        if not self.rss_url:
            self.clear_last_refresh_error()
            return

        self.assert_not_deleted()

        log.info('Refreshing %s', self)
        self.last_refresh_attempt = int(helpers.now())

        try:
            self._refresh()
            self.last_refresh_error = None
            ret = None
        except Exception as exc:
            self.last_refresh_error = traceback.format_exc()
            ret = worms.raise_without_rollback(exc)

        pairs = {
            'id': self.id,
            'last_refresh_attempt': self.last_refresh_attempt,
            'last_refresh_error': self.last_refresh_error,
        }
        self.bringdb.update(table=Feed, pairs=pairs, where_key='id')
        return ret

    @worms.atomic
    def refresh_all(self):
        '''
        Refresh this feed and all of its descendants, except the ones with
        refresh_with_others set to False.
        '''
        predicate = lambda feed: feed.refresh_with_others
        # The predicate does not apply to the yielded self, which is good
        # because the user specifically called this function so we should
        # refresh the self regardless of the predicate.
        feeds = list(self.walk_children(predicate=predicate, yield_self=True))
        for feed in feeds:
            try:
                feed.refresh()
            except Exception:
                log.warning(traceback.format_exc())

    @worms.atomic
    def set_autorefresh_interval(self, autorefresh_interval):
        self.assert_not_deleted()
        autorefresh_interval = self.normalize_autorefresh_interval(autorefresh_interval)

        pairs = {
            'id': self.id,
            'autorefresh_interval': autorefresh_interval,
        }
        self.bringdb.update(table=Feed, pairs=pairs, where_key='id')
        self.autorefresh_interval = autorefresh_interval

    @worms.atomic
    def set_description(self, description):
        self.assert_not_deleted()
        description = self.normalize_description(description)

        pairs = {
            'id': self.id,
            'description': description,
        }
        self.bringdb.update(table=Feed, pairs=pairs, where_key='id')
        self.description = description

    def _set_icon_by_domain_favicon(self):
        parts = urllib.parse.urlsplit(self.rss_url)

        for path in ['/favicon.ico', '/favicon.png']:
            url = urllib.parse.urlunsplit(parts._replace(path=path, query='', fragment=''))
            log.debug('Trying favicon %s', url)
            response = constants.http_session.get(url)
            if response.ok:
                try:
                    self.set_icon(response.content)
                    return self.icon
                except Exception:
                    log.warning(traceback.format_exc())

    @worms.atomic
    def set_filters(self, filters):
        self.assert_not_deleted()

        unique = set()
        filters = list(filters)
        for filt in filters:
            if not isinstance(filt, Filter):
                raise TypeError(filt)

            filt.assert_not_deleted()

            if filt in unique:
                raise TypeError(f'{filt} was provided in the list twice.')
            unique.add(filt)

        self.bringdb.delete(table='feed_filter_rel', pairs={'feed_id': self.id})
        for (index, filt) in enumerate(filters):
            data = {
                'feed_id': self.id,
                'filter_id': filt.id,
                'order_rank': index + 1,
            }
            self.bringdb.insert(table='feed_filter_rel', pairs=data)

    @worms.atomic
    def set_http_headers(self, http_headers):
        self.assert_not_deleted()
        http_headers = self.normalize_http_headers(http_headers)

        pairs = {
            'id': self.id,
            'http_headers': self.normalize_http_headers_json(http_headers),
        }
        self.bringdb.update(table=Feed, pairs=pairs, where_key='id')
        self.http_headers = http_headers

    @worms.atomic
    def set_icon(self, icon:bytes):
        self.assert_not_deleted()
        icon = self.normalize_icon(icon)

        pairs = {
            'id': self.id,
            'icon': icon,
        }
        self.bringdb.update(table=Feed, pairs=pairs, where_key='id')
        self.icon = icon

    @worms.atomic
    def set_isolate_guids(self, isolate_guids):
        self.assert_not_deleted()
        isolate_guids = self.normalize_isolate_guids(isolate_guids)

        pairs = {
            'id': self.id,
            'isolate_guids': isolate_guids,
        }
        self.bringdb.update(table=Feed, pairs=pairs, where_key='id')

        pairs = {
            'original_feed_id': self.id,
        }
        if isolate_guids:
            pairs['rss_guid'] = sqlhelpers.Inject(f'"_isolate_{self.id}_"||rss_guid')
        else:
            pairs['rss_guid'] = sqlhelpers.Inject(f'REPLACE(rss_guid, "_isolate_{self.id}_", "")')

        self.bringdb.update(table=News, pairs=pairs, where_key='original_feed_id')
        self.isolate_guids = isolate_guids

    @worms.atomic
    def set_parent(self, parent, ui_order_rank=None):
        self.assert_not_deleted()
        if parent is None:
            parent_id = None

        else:
            if not isinstance(parent, Feed):
                raise TypeError(parent)

            if parent == self:
                raise TypeError(parent)

            if parent in list(self.walk_children()):
                raise TypeError(parent)

            parent.assert_not_deleted()
            parent_id = parent.id

        pairs = {
            'id': self.id,
            'parent_id': parent_id,
        }

        if ui_order_rank is not None:
            ui_order_rank = self.normalize_ui_order_rank(ui_order_rank)
            pairs['ui_order_rank'] = ui_order_rank
            self.ui_order_rank = ui_order_rank

        self.bringdb.update(table=Feed, pairs=pairs, where_key='id')
        self.bringdb.reassign_ui_order_ranks()
        self.parent_id = parent_id

        if parent is not None:
            self._parent = parent

    @worms.atomic
    def set_refresh_with_others(self, refresh_with_others):
        self.assert_not_deleted()
        refresh_with_others = self.normalize_refresh_with_others(refresh_with_others)

        pairs = {
            'id': self.id,
            'refresh_with_others': refresh_with_others,
        }
        self.bringdb.update(table=Feed, pairs=pairs, where_key='id')
        self.refresh_with_others = refresh_with_others

    @worms.atomic
    def set_rss_url(self, rss_url):
        self.assert_not_deleted()
        rss_url = self.normalize_rss_url(rss_url)

        pairs = {
            'id': self.id,
            'rss_url': rss_url,
        }
        self.bringdb.update(table=Feed, pairs=pairs, where_key='id')
        self.rss_url = rss_url

    @worms.atomic
    def set_title(self, title):
        self.assert_not_deleted()
        title = self.normalize_title(title)

        pairs = {
            'id': self.id,
            'title': title,
        }
        self.bringdb.update(table=Feed, pairs=pairs, where_key='id')
        self.title = title

    @worms.atomic
    def set_ui_order_rank(self, ui_order_rank):
        self.assert_not_deleted()
        ui_order_rank = self.normalize_ui_order_rank(ui_order_rank)

        pairs = {
            'id': self.id,
            'ui_order_rank': ui_order_rank,
        }
        self.bringdb.update(table=Feed, pairs=pairs, where_key='id')
        self.ui_order_rank = ui_order_rank

    @worms.atomic
    def set_web_url(self, web_url):
        self.assert_not_deleted()
        web_url = self.normalize_web_url(web_url)

        pairs = {
            'id': self.id,
            'web_url': web_url,
        }
        self.bringdb.update(table=Feed, pairs=pairs, where_key='id')
        self.web_url = web_url

    def walk_children(self, *, predicate=None, yield_self=True) -> typing.Iterable:
        '''
        Yield all of the descendant Feeds below this one.

        predicate:
            You can provide a function which accepts one argument, the Feed, and
            returns True or False. If it is True, we will yield that feed and
            its descendants. If it is False, we will not yield that Feed or its
            descendants. This is better than using a comprehension on the output
            of this generator because it prevents walking entire trees that you
            don't want.

        yield_self:
            If True, this instance is yielded as the first result. The predicate
            function is not applied to self because if you didn't want to walk
            this feed you wouldn't have called here!
        '''
        # When yield_self is false we don't apply the predicate to self, only
        # the children.
        if yield_self:
            yield self

        for child in self.get_children():
            if predicate is None or predicate(child):
                yield from child.walk_children()

    def walk_parents(self, yield_self=False):
        '''
        Yield all of the ancestor Feeds above this one.

        yield_self:
            If True, this instance is yielded as the first result.
        '''
        if yield_self:
            yield self

        current = self.parent
        while current is not None:
            yield current
            current = current.parent

class Filter(ObjectBase):
    table = 'filters'
    no_such_exception = exceptions.NoSuchFilter
    THEN_CONTINUE_FILTERS = sentinel.Sentinel('then_continue_filters')
    THEN_STOP_FILTERS = sentinel.Sentinel('then_stop_filters')

    def __init__(self, bringdb, db_row):
        super().__init__(bringdb)

        self.id = db_row['id']
        self.name = db_row['name']

        # Because the user may have tinkered with the database while the
        # application was off, or deleted a script referred to by send_to_py,
        # we can't just let the application blow up on next launch. Those broken
        # filters may eventually cause problems but we need to at least let them
        # instantiate.
        self._conditions = db_row['conditions']
        self.conditions = self.parse_conditions(self._conditions, run_validator=False)
        try:
            self.parse_conditions(self._conditions, run_validator=True)
        except Exception:
            message = f'The conditions for {self} as stored in the database do not pass validation.'
            message += '\n' + traceback.format_exc()
            log.warning(message)

        self._actions = db_row['actions']
        self.actions = self.parse_actions(self._actions, run_validator=False)
        try:
            self.parse_actions(self._actions, run_validator=True)
        except Exception:
            message = f'The actions for {self} as stored in the database do not pass validation.'
            message += '\n' + traceback.format_exc()
            log.warning(message)

    def __repr__(self):
        if self.name:
            return f'Filter:{self.id}:{self.name}'
        else:
            return f'Filter:{self.id}'

    @staticmethod
    def _parse_stored(token:str, action_or_condition:str, run_validator=True) -> types.FunctionType:
        '''
        Given an action string as it is stored in the database, return a partial
        function that takes in the News object and performs the action with the
        other argument already included.

        E.g.
        ('move_to_feed:0123456789', 'action')
        -> lambda news: Filter._action_move_to_feed(news, '0123456789")

        ('text_regex:my keyword', 'condition')
        -> lambda news: Filter._condition_text_regex(news, 'my keyword')
        '''
        if not isinstance(token, str):
            raise TypeError(token)

        if action_or_condition == 'action':
            getter = Filter._get_action_function
            exc_class = exceptions.InvalidFilterAction
        elif action_or_condition == 'condition':
            getter = Filter._get_condition_function
            exc_class = exceptions.InvalidFilterCondition
        else:
            raise ValueError(action_or_condition)

        parts = token.split(':', 1)
        name = parts[0]
        (function, validator) = getter(name)

        # Functions without an argument only take the news object for a count
        # of 1. Functions with an argument have a count of two.
        expects_argument = len(inspect.signature(function).parameters) == 2

        if len(parts) == 1:
            if expects_argument:
                raise exc_class(f'{action_or_condition} {name} takes 1 argument, not given in "{token}".')
            return function

        if len(parts) == 2:
            if not expects_argument:
                raise exc_class(f'{action_or_condition} {name} takes 0 arguments, given in "{token}".')
            argument = parts[1]
            if validator is not None and run_validator:
                validator(argument)
            return lambda news: function(news, argument)

    ## Actions

    @staticmethod
    def _action_send_to_py(news, path):
        '''
        Raises pathclass.NotFile if file does not exist.
        Raises ValueError if file's basename cannot be a Python identifier.
        '''
        module = helpers.import_module_by_path(path)
        log.info('Running external script %s with %s', path, news)
        status = module.main(news)
        if status != 0:
            raise ValueError(status)
        return Filter.THEN_CONTINUE_FILTERS

    @staticmethod
    def _action_send_to_py_validate(path):
        # Note: as long as the server is in demo mode, the @transaction of
        # set_actions will never actually reach this point in the code, and we
        # should not leak information about existent / nonexistent files on
        # our system.
        try:
            helpers.import_module_by_path(path)
        except pathclass.NotFile as exc:
            raise exceptions.InvalidFilterAction(f'{exc.args[0]} is not a python file.')
        except Exception as exc:
            raise exceptions.InvalidFilterAction(str(exc))

    @staticmethod
    def _action_move_to_feed(news, feed_id):
        '''
        Raises exceptions.NoSuchFeed if feed_id does not exist.
        '''
        feed = news.bringdb.get_feed(feed_id)
        feed.assert_not_deleted()
        if news.feed_id != feed.id:
            news.move_to_feed(feed)
        return Filter.THEN_CONTINUE_FILTERS

    @staticmethod
    def _action_move_to_feed_validate(feed_id):
        # I want to make this work, but it creates a cascading effect where
        # everything leading up to this point can't be staticmethod, most
        # importantly when we're doing BringDB.add_filter and the Filter
        # instance doesn't exist yet, so we can't even use a self! We could
        # pass the BringDB on its own to provide the instance context
        # necessary for this function, but it's gonna look super jank.
        pass
        # try:
        #     self.bringdb.get_feed(feed_id)
        # except exceptions.NoSuchFeed:
        #     raise exceptions.InvalidFilterAction(f'Feed {feed_id} does not exist.')

    @staticmethod
    def _jank_validate_move_to_feed(bringdb, actions:str):
        # For the time being, since this is the only action that requires
        # context from the BringDB, I'm just gonna single it out and call it
        # separately.
        # We operate on the actions:str as input instead of the actions:list
        # because we need to be able to call this from BringDB.add_filter,
        # which uses the normalizer function but not the parser function.
        # I mean I could make it happen but oh well.
        for line in actions.splitlines():
            if 'move_to_feed' not in line:
                continue
            if ':' not in line:
                # We're going to skip this for now and let the other normalize &
                # parse step pick it up. It already has code for validating
                # argument counts.
                continue
            feed_id = line.split(':', 1)[1].strip()
            try:
                bringdb.get_feed(feed_id)
            except exceptions.NoSuchFeed:
                raise exceptions.InvalidFilterAction(f'Feed "{feed_id}" does not exist.')

    @staticmethod
    def _action_set_read(news, read):
        read = stringtools.truthystring(read)
        if read != news.read:
            news.set_read(read)
        return Filter.THEN_CONTINUE_FILTERS

    @staticmethod
    def _action_set_read_validate(read):
        if read in stringtools.TRUTHYSTRING_TRUE:
            return
        if read in stringtools.TRUTHYSTRING_FALSE:
            return

        raise exceptions.InvalidFilterAction(f'set_read argument should be true or false, not "{read}".')

    @staticmethod
    def _action_set_recycled(news, recycled):
        recycled = stringtools.truthystring(recycled)
        if recycled != news.recycled:
            news.set_recycled(recycled)
        return Filter.THEN_CONTINUE_FILTERS

    @staticmethod
    def _action_set_recycled_validate(recycled):
        if recycled in stringtools.TRUTHYSTRING_TRUE:
            return
        if recycled in stringtools.TRUTHYSTRING_FALSE:
            return

        raise exceptions.InvalidFilterAction(f'set_recycled argument should be true or false, not {recycled}.')

    @staticmethod
    def _action_then_continue_filters(news):
        return Filter.THEN_CONTINUE_FILTERS

    @staticmethod
    def _action_then_stop_filters(news):
        return Filter.THEN_STOP_FILTERS

    @staticmethod
    def _function_list(action_or_condition, arg_count):
        results = []
        for (name, function) in sorted(vars(Filter).items()):
            if not name.startswith(f'_{action_or_condition}_'):
                continue
            if name.endswith('validate'):
                continue
            name = name.replace(f'_{action_or_condition}_', '')
            sig = inspect.signature(function.__func__)
            if len(sig.parameters) != arg_count + 1:
                continue

            if len(sig.parameters) == 1:
                results.append(name)
            else:
                arg = list(sig.parameters)[1]
                results.append(f'{name}:{arg}')

        return results

    @staticmethod
    def _assert_valid_actions(actions:list):
        if not isinstance(actions, list):
            raise TypeError(actions)

        if len(actions) == 0:
            raise exceptions.InvalidFilterAction('No actions')

        if len(actions) == 1 and actions[0] == Filter._action_then_continue_filters:
            raise exceptions.InvalidFilterAction('There is no point having then_continue_filters be the only action.')

        last_actions = {Filter._action_then_stop_filters, Filter._action_then_continue_filters}
        for (index, action) in enumerate(actions):
            is_last_index = (index == (len(actions) - 1))
            if action in last_actions and not is_last_index:
                raise exceptions.InvalidFilterAction(f'then_continue_filters, then_stop_filters can only be the last action.')
            if action not in last_actions and is_last_index:
                raise exceptions.InvalidFilterAction(f'The last action must be either then_continue_filters or then_stop_filters.')

        return actions

    @staticmethod
    def _get_action_function(name:str):
        '''
        Given the name of an action like 'move_to_feed', return the function
        Filter._action_move_to_feed.
        '''
        if not isinstance(name, str):
            raise TypeError(f'action {name} should be {str}, not {type(name)}.')

        name = name.strip()

        if not name.isidentifier():
            raise exceptions.InvalidFilterAction(f'{repr(name)} doesn\'t look like a valid identifier.')

        function = getattr(Filter, f'_action_{name}', None)
        if function is None:
            raise exceptions.InvalidFilterAction(f'No action function called {repr(name)}.')

        validator = getattr(Filter, f'_action_{name}_validate', None)

        return (function, validator)

    @staticmethod
    def _parse_stored_action(token, run_validator):
        return Filter._parse_stored(token, 'action', run_validator=run_validator)

    ## Conditions

    @staticmethod
    def _condition_always(news) -> bool:
        return True

    @staticmethod
    def _condition_anywhere_regex(news, pattern) -> bool:
        return (
            Filter._condition_enclosure_regex(news, pattern) or
            Filter._condition_title_regex(news, pattern) or
            Filter._condition_text_regex(news, pattern) or
            Filter._condition_url_regex(news, pattern)
        )

    @staticmethod
    def _condition_enclosure_regex(news, pattern) -> bool:
        for enclosure in news.enclosures:
            if not enclosure.get('url', None):
                continue
            if re.search(pattern, enclosure['url'], flags=re.I):
                return True

        return False

    @staticmethod
    def _condition_is_read(news) -> bool:
        return bool(news.read)

    @staticmethod
    def _condition_is_recycled(news) -> bool:
        return bool(news.recycled)

    @staticmethod
    def _condition_has_enclosure(news) -> bool:
        return len(news.enclosures) > 0

    @staticmethod
    def _condition_has_text(news) -> bool:
        return bool(news.text)

    @staticmethod
    def _condition_has_url(news) -> bool:
        return bool(news.web_url)

    @staticmethod
    def _condition_text_regex(news, pattern) -> bool:
        return bool(news.text) and bool(re.search(pattern, news.text, flags=re.I))

    @staticmethod
    def _condition_title_regex(news, pattern) -> bool:
        return bool(news.title) and bool(re.search(pattern, news.title, flags=re.I))

    @staticmethod
    def _condition_url_regex(news, pattern) -> bool:
        return bool(news.web_url) and bool(re.search(pattern, news.web_url, flags=re.I))

    @staticmethod
    def _get_condition_function(name:str):
        '''
        Given the name of a condition like 'has_enclosure', return the function
        Filter._condition_has_enclosure.
        '''
        if not isinstance(name, str):
            raise TypeError(f'condition {name} should be {str}, not {type(name)}.')

        name = name.strip()

        if not name.isidentifier():
            raise exceptions.InvalidFilterCondition(f'{repr(name)} doesn\'t look like a valid identifier.')

        function = getattr(Filter, f'_condition_{name}', None)
        if function is None:
            raise exceptions.InvalidFilterCondition(f'No condition function called {repr(name)}.')

        validator = getattr(Filter, f'_condition_{name}_validate', None)

        return (function, validator)

    @staticmethod
    def _parse_stored_condition(token, run_validator):
        return Filter._parse_stored(token, 'condition', run_validator=run_validator)

    ##

    @worms.atomic
    def delete(self):
        self.assert_not_deleted()

        # Look for feeds that use this filter.
        feed_ids = self.bringdb.select_column(
            'SELECT feed_id FROM feed_filter_rel WHERE filter_id == ?',
            [self.id],
        )
        feeds = list(self.bringdb.get_feeds_by_id(list(feed_ids)))
        if len(feeds) > 0:
            raise exceptions.FilterStillInUse(filter=self, feeds=feeds)

        # No turning back
        log.info('Deleting %s.', self)
        self.bringdb.delete(table=Filter, pairs={'id': self.id})
        self.deleted = True

    @property
    def display_name(self):
        if self.name is not None:
            return self.name

        return str(self.id)

    def jsonify(self):
        self.assert_not_deleted()
        j = {
            'type': 'filter',
            'id': self.id,
            'name': self.name,
            'display_name': self.display_name,
            'conditions': self._conditions,
            'actions': self._actions,
        }
        return j

    @staticmethod
    def normalize_actions(actions:str) -> str:
        if not isinstance(actions, str):
            raise TypeError(actions)
        actions = [line.strip() for line in actions.splitlines()]
        actions = [line for line in actions if line]
        actions = '\n'.join(actions)
        # We do not return the parsed, we just use it to test for validity.
        Filter.parse_actions(actions)
        return actions

    @staticmethod
    def normalize_conditions(conditions:str) -> str:
        # conditions = re.sub(r'([\\])', r'\\\1', conditions)
        conditions = expressionmatch.ExpressionTree.parse(conditions)
        # This is what we're going to return so that the database stores the
        # normalized string.
        conditions = str(conditions)
        # But we also need to perform this step to make sure it doesn't raise.
        Filter.parse_conditions(conditions)
        return conditions

    normalize_name = helpers.normalize_string_blank_to_none

    @staticmethod
    def parse_actions(actions:str, run_validator=True):
        actions = actions.split('\n')
        actions = [Filter._parse_stored_action(action, run_validator=run_validator) for action in actions]
        Filter._assert_valid_actions(actions)
        return actions

    @staticmethod
    def parse_conditions(conditions:str, run_validator=True):
        conditions = expressionmatch.ExpressionTree.parse(conditions)
        conditions.map(lambda token: Filter._parse_stored_condition(token, run_validator=run_validator))
        return conditions

    @worms.atomic
    def process_news(self, news):
        # Because we called self.conditions.map(parse_stored_condition), all of
        # the tokens inside the ExpressionTree are now partialed functions that
        # are ready to receive the news object under test as the sole argument,
        # and return True / False. The ExpressionTree will compute the final
        # decision.
        match = self.conditions.evaluate(
            news,
            match_function=lambda news, condition: condition(news),
        )
        if not match:
            log.loud('%s does not match %s.', news, self)
            return Filter.THEN_CONTINUE_FILTERS

        log.loud('%s matches %s.', news, self)
        for action in self.actions:
            status = action(news)
            if status is Filter.THEN_STOP_FILTERS:
                return Filter.THEN_STOP_FILTERS
            if status is not Filter.THEN_CONTINUE_FILTERS:
                raise TypeError(f'{repr(status)} should have been {repr(Filter.THEN_CONTINUE_FILTERS)}.')

        return Filter.THEN_CONTINUE_FILTERS

    @worms.atomic
    def set_actions(self, actions:str):
        self.assert_not_deleted()
        actions = self.normalize_actions(actions)
        self._jank_validate_move_to_feed(self.bringdb, actions)

        pairs = {
            'id': self.id,
            'actions': actions,
        }
        self.bringdb.update(table=Filter, pairs=pairs, where_key='id')
        self._actions = actions
        self.actions = self.parse_actions(actions)

    @worms.atomic
    def set_conditions(self, conditions:str):
        self.assert_not_deleted()
        # Note that the database is given the input string, not the normalize
        # return value. If there's a problem, normalize will raise an exception.
        conditions = self.normalize_conditions(conditions)

        pairs = {
            'id': self.id,
            'conditions': conditions,
        }
        self.bringdb.update(table=Filter, pairs=pairs, where_key='id')
        self._conditions = conditions
        self.conditions = self.parse_conditions(conditions)

    @worms.atomic
    def set_name(self, name):
        self.assert_not_deleted()
        name = self.normalize_name(name)

        pairs = {
            'id': self.id,
            'name': name,
        }
        self.bringdb.update(table=Filter, pairs=pairs, where_key='id')
        self.name = name

class News(ObjectBase):
    table = 'news'
    no_such_exception = exceptions.NoSuchNews

    def __init__(self, bringdb, db_row):
        super().__init__(bringdb)

        self.id = db_row['id']
        self.feed_id = db_row['feed_id']
        self.original_feed_id = db_row['original_feed_id']
        self.rss_guid = db_row['rss_guid']
        self.updated = db_row['updated']
        self.title = db_row['title']
        self.text = db_row['text']
        self.web_url = db_row['web_url']
        self.comments_url = db_row['comments_url']
        self.created = db_row['created']
        self.read = db_row['read']
        self.recycled = db_row['recycled']

        self.published_unix = db_row['published']
        # utcfromtimestamp doesn't like negative numbers, but timedelta can
        # handle it, so this does better than just calling
        # utcfromtimestamp(published)
        self.published = datetime.datetime.utcfromtimestamp(0) + datetime.timedelta(seconds=self.published_unix)

        if db_row['authors']:
            self.authors = json.loads(db_row['authors'])
        else:
            self.authors = []
        if db_row['enclosures']:
            self.enclosures = json.loads(db_row['enclosures'])
        else:
            self.enclosures = []

        self._feed = None

    def __repr__(self):
        if self.title:
            return f'News:{self.id}:{self.title}'
        else:
            return f'News:{self.id}'

    normalize_author_name = helpers.normalize_string_blank_to_none

    normalize_author_email = helpers.normalize_string_blank_to_none

    normalize_author_uri = helpers.normalize_string_blank_to_none

    @staticmethod
    def _prune_json_dicts(dicts):
        '''
        For the purposes of storing the authors and enclosures JSON, let's prune
        all the keys with null values and remove the element altogether if it
        only has null values. Since JSON storage is more wasteful than real
        columns there's no point storing a bunch of "null" strings.
        '''
        # Prune empty attributes to save DB space.
        dicts = [
            {key: value for (key, value) in d.items() if value}
            for d in dicts
        ]
        # Prune empty dicts to save DB space.
        dicts = [d for d in dicts if len(d) > 0]
        return dicts

    @staticmethod
    def normalize_authors(authors) -> list[dict]:
        if authors is None:
            return []

        if isinstance(authors, str):
            authors = json.loads(authors)

        authors = list(authors)
        for author in authors:
            author['name'] = News.normalize_author_name(author.get('name'))
            author['email'] = News.normalize_author_email(author.get('email'))
            author['uri'] = News.normalize_author_uri(author.get('uri'))

        return News._prune_json_dicts(authors)

    @staticmethod
    def normalize_authors_json(authors):
        authors = News.normalize_authors(authors)
        if len(authors) == 0:
            return None
        return json.dumps(authors)

    normalize_comments_url = helpers.normalize_string_blank_to_none

    normalize_enclosure_type = helpers.normalize_string_blank_to_none

    normalize_enclosure_url = helpers.normalize_string_blank_to_none

    normalize_enclosure_size = helpers.normalize_int_or_none

    @staticmethod
    def normalize_enclosures(enclosures) -> list[dict]:
        if enclosures is None:
            return []

        if isinstance(enclosures, str):
            enclosures = json.loads(enclosures)

        enclosures = list(enclosures)
        for enclosure in enclosures:
            enclosure['type'] = News.normalize_enclosure_type(enclosure.get('type'))
            enclosure['url'] = News.normalize_enclosure_url(enclosure.get('url'))
            enclosure['size'] = News.normalize_enclosure_size(enclosure.get('size'))

        return News._prune_json_dicts(enclosures)

    @staticmethod
    def normalize_enclosures_json(enclosures):
        enclosures = News.normalize_enclosures(enclosures)
        if len(enclosures) == 0:
            return None
        return json.dumps(enclosures)

    @staticmethod
    def normalize_published(published):
        if isinstance(published, (int, float)):
            return published

        if isinstance(published, str):
            return helpers.dateutil_parse(published).timestamp()

        raise TypeError(published)

    @staticmethod
    def normalize_read(read):
        if not isinstance(read, bool):
            raise TypeError(read)

        return read

    @staticmethod
    def normalize_recycled(recycled):
        if not isinstance(recycled, bool):
            raise TypeError(recycled)

        return recycled

    normalize_rss_guid = helpers.normalize_string_not_blank

    normalize_text = helpers.normalize_string_blank_to_none

    normalize_title = helpers.normalize_string_blank_to_none

    @staticmethod
    def normalize_updated(updated):
        if isinstance(updated, (int, float)):
            return updated

        if isinstance(updated, str):
            return helpers.dateutil_parse(updated).timestamp()

        raise TypeError(updated)

    normalize_web_url = helpers.normalize_string_blank_to_none

    @property
    def feed(self):
        if self._feed is None:
            self._feed = self.bringdb.get_feed(self.feed_id)

        return self._feed

    def jsonify(self, complete=False):
        self.assert_not_deleted()
        j = {
            'type': 'news',
            'id': self.id,
            'authors': self.authors,
            'comments_url': self.comments_url,
            'created': self.created,
            'enclosures': self.enclosures,
            'feed_id': self.feed_id,
            'published_unix': self.published_unix,
            'published_string': self.published_string,
            'published_string_local': self.published_string_local,
            'read': self.read,
            'recycled': self.recycled,
            'rss_guid': self.rss_guid,
            'title': self.title,
            'updated': self.updated,
            'web_url': self.web_url,
        }
        if complete:
            j['text'] = self.text

        return j

    @worms.atomic
    def move_to_feed(self, feed):
        self.assert_not_deleted()

        if not isinstance(feed, Feed):
            raise TypeError(feed)

        feed.assert_not_deleted()

        if self.feed == feed:
            raise ValueError(feed)

        log.debug('Moving %s to %s.', self, feed)

        pairs = {
            'id': self.id,
            'feed_id': feed.id,
        }
        self.bringdb.update(table=News, pairs=pairs, where_key='id')
        self.feed_id = feed.id
        self._feed = None

    @property
    def published_string(self):
        published = self.published.strftime('%Y-%m-%d %H:%M')
        return published

    @property
    def published_string_local(self):
        return self.published.astimezone().strftime('%Y-%m-%d %H:%M')

    @worms.atomic
    def set_read(self, read):
        self.assert_not_deleted()
        read = self.normalize_read(read)

        pairs = {
            'id': self.id,
            'read': read,
        }
        self.bringdb.update(table=News, pairs=pairs, where_key='id')
        self.read = read

    @worms.atomic
    def set_recycled(self, recycled):
        self.assert_not_deleted()
        recycled = self.normalize_recycled(recycled)

        pairs = {
            'id': self.id,
            'recycled': recycled,
        }
        self.bringdb.update(table=News, pairs=pairs, where_key='id')
        self.recycled = recycled
