import bs4
import random
import sqlite3
import typing

from . import constants
from . import exceptions
from . import helpers
from . import objects

from voussoirkit import cacheclass
from voussoirkit import pathclass
from voussoirkit import sentinel
from voussoirkit import sqlhelpers
from voussoirkit import vlogging
from voussoirkit import worms

log = vlogging.get_logger(__name__)

RNG = random.SystemRandom()

####################################################################################################

class BDBFeedMixin:
    def __init__(self):
        super().__init__()

    @worms.atomic
    def add_feed(
            self,
            *,
            autorefresh_interval=86400,
            description=None,
            icon=None,
            isolate_guids=False,
            parent=None,
            refresh_with_others=True,
            rss_url=None,
            title=None,
            web_url=None,
            ui_order_rank=None,
        ):
        if parent is None:
            parent_id = None
        else:
            if not isinstance(parent, objects.Feed):
                raise TypeError(parent)
            parent.assert_not_deleted()
            parent_id = parent.id

        autorefresh_interval = objects.Feed.normalize_autorefresh_interval(autorefresh_interval)
        refresh_with_others = objects.Feed.normalize_refresh_with_others(refresh_with_others)
        rss_url = objects.Feed.normalize_rss_url(rss_url)
        web_url = objects.Feed.normalize_web_url(web_url)
        title = objects.Feed.normalize_title(title)
        description = objects.Feed.normalize_description(description)
        icon = objects.Feed.normalize_icon(icon)
        isolate_guids = objects.Feed.normalize_isolate_guids(isolate_guids)
        if ui_order_rank is None:
            ui_order_rank = self.get_last_ui_order_rank() + 1
        else:
            ui_order_rank = objects.Feed.normalize_ui_order_rank(ui_order_rank)

        data = {
            'id': self.generate_id(objects.Feed),
            'parent_id': parent_id,
            'rss_url': rss_url,
            'web_url': web_url,
            'title': title,
            'description': description,
            'created': helpers.now(),
            'refresh_with_others': refresh_with_others,
            'last_refresh': 0,
            'last_refresh_attempt': 0,
            'last_refresh_error': None,
            'autorefresh_interval': autorefresh_interval,
            'http_headers': None,
            'isolate_guids': isolate_guids,
            'icon': icon,
            'ui_order_rank': ui_order_rank,
        }
        self.insert(table=objects.Feed, pairs=data)
        feed = self.get_cached_instance(objects.Feed, data)
        return feed

    def get_bulk_unread_counts(self):
        '''
        Instead of calling feed.get_unread_count() on many separate feed objects
        and performing lots of duplicate work, you can call here and get them
        all at once with much less database access. I brought my /feeds.json
        down from 160ms to 6ms by using this.

        Missing keys means 0 unread.
        '''
        # Even though we have api functions for all of this, I want to squeeze
        # out the perf. This function is meant to be used in situations where
        # speed matters more than code beauty.
        feeds = {feed.id: feed for feed in self.get_feeds()}
        childs = {}
        for feed in feeds.values():
            if feed.parent_id:
                childs.setdefault(feed.parent_id, []).append(feed)
        roots = [feed for feed in feeds.values() if not feed.parent_id]

        query = '''
        SELECT feed_id, COUNT(rowid)
        FROM news
        WHERE recycled == 0 AND read == 0
        GROUP BY feed_id
        '''
        counts = {feeds[feed_id]: count for (feed_id, count) in self.select(query)}

        def recursive_update(feed):
            counts.setdefault(feed, 0)
            children = childs.get(feed.id, None)
            if children:
                counts[feed] += sum(recursive_update(child) for child in children)
                pass
            return counts[feed]

        for root in roots:
            recursive_update(root)

        return counts

    def get_feed(self, id) -> objects.Feed:
        return self.get_object_by_id(objects.Feed, id)

    def get_feed_count(self) -> int:
        return self.select_one_value('SELECT COUNT(id) FROM feeds')

    def get_feeds(self) -> typing.Iterable[objects.Feed]:
        query = 'SELECT * FROM feeds ORDER BY ui_order_rank ASC'
        return self.get_objects_by_sql(objects.Feed, query)

    def get_feeds_by_id(self, ids) -> typing.Iterable[objects.Feed]:
        return self.get_objects_by_id(objects.Feed, ids)

    def get_feeds_by_sql(self, query, bindings=None) -> typing.Iterable[objects.Feed]:
        return self.get_objects_by_sql(objects.Feed, query, bindings)

    def get_last_ui_order_rank(self) -> int:
        query = 'SELECT ui_order_rank FROM feeds ORDER BY ui_order_rank DESC LIMIT 1'
        rank = self.select_one_value(query)
        if rank is None:
            return 0
        return rank

    def get_root_feeds(self) -> typing.Iterable[objects.Feed]:
        query = 'SELECT * FROM feeds WHERE parent_id IS NULL ORDER BY ui_order_rank ASC'
        return self.get_objects_by_sql(objects.Feed, query)

    @worms.atomic
    def reassign_ui_order_ranks(self):
        feeds = list(self.get_root_feeds())
        rank = 1
        for feed in feeds:
            for descendant in feed.walk_children():
                descendant.set_ui_order_rank(rank)
                rank += 1

####################################################################################################

class BDBFilterMixin:
    def __init__(self):
        super().__init__()

    @worms.atomic
    def add_filter(self, name, conditions, actions):
        name = objects.Filter.normalize_name(name)
        conditions = objects.Filter.normalize_conditions(conditions)
        actions = objects.Filter.normalize_actions(actions)
        objects.Filter._jank_validate_move_to_feed(bringdb=self, actions=actions)

        data = {
            'id': self.generate_id(objects.Filter),
            'name': name,
            'created': helpers.now(),
            'conditions': conditions,
            'actions': actions,
        }
        self.insert(table=objects.Filter, pairs=data)
        filt = self.get_cached_instance(objects.Filter, data)
        return filt

    def get_filter(self, id) -> objects.Filter:
        return self.get_object_by_id(objects.Filter, id)

    def get_filter_count(self) -> int:
        return self.select_one_value('SELECT COUNT(id) FROM filters')

    def get_filters(self) -> typing.Iterable[objects.Filter]:
        return self.get_objects(objects.Filter)

    def get_filters_by_id(self, ids) -> typing.Iterable[objects.Filter]:
        return self.get_objects_by_id(objects.Filter, ids)

    def get_filters_by_sql(self, query, bindings=None) -> typing.Iterable[objects.Filter]:
        return self.get_objects_by_sql(objects.Filter, query, bindings)

    @worms.atomic
    def process_news_through_filters(self, news):
        def prepare_filters(feed):
            filters = []
            for ancestor in feed.walk_parents(yield_self=True):
                filters.extend(ancestor.get_filters())
            return filters

        feed = news.feed
        original_feed = feed
        filters = prepare_filters(feed)
        status = objects.Filter.THEN_CONTINUE_FILTERS
        too_many_switches = 20

        while feed and filters and status is objects.Filter.THEN_CONTINUE_FILTERS:
            filt = filters.pop(0)
            status = filt.process_news(news)

            switched_feed = news.feed
            if switched_feed == feed:
                continue

            feed = switched_feed
            filters = prepare_filters(feed)

            too_many_switches -= 1
            if too_many_switches > 0:
                continue
            raise Exception(f'{news} from {original_feed} got moved too many times. Something wrong?')

####################################################################################################

class BDBNewsMixin:
    DUPLICATE_BAIL = sentinel.Sentinel('duplicate bail')

    def __init__(self):
        super().__init__()

    @worms.atomic
    def add_news(
            self,
            *,
            authors,
            comments_url,
            enclosures,
            feed,
            published,
            rss_guid,
            text,
            title,
            updated,
            web_url,
        ):
        if not isinstance(feed, objects.Feed):
            raise TypeError(feed)
        feed.assert_not_deleted()

        rss_guid = objects.News.normalize_rss_guid(rss_guid)
        if feed.isolate_guids:
            rss_guid = f'_isolate_{feed.id}_{rss_guid}'

        published = objects.News.normalize_published(published)
        updated = objects.News.normalize_updated(updated)
        title = objects.News.normalize_title(title)
        text = objects.News.normalize_text(text)
        web_url = objects.News.normalize_web_url(web_url)
        comments_url = objects.News.normalize_comments_url(comments_url)
        authors = objects.News.normalize_authors_json(authors)
        enclosures = objects.News.normalize_enclosures_json(enclosures)

        data = {
            'id': self.generate_id(objects.News),
            'feed_id': feed.id,
            'original_feed_id': feed.id,
            'rss_guid': rss_guid,
            'published': published,
            'updated': updated,
            'title': title,
            'text': text,
            'web_url': web_url,
            'comments_url': comments_url,
            'created': helpers.now(),
            'read': False,
            'recycled': False,
            'authors': authors,
            'enclosures': enclosures,
        }
        self.insert(table=objects.News, pairs=data)
        news = self.get_cached_instance(objects.News, data)
        return news

    def get_news(self, id) -> objects.News:
        return self.get_object_by_id(objects.News, id)

    def get_news_count(self) -> int:
        return self.select_one_value('SELECT COUNT(id) FROM news')

    def get_newss(
            self,
            *,
            read=False,
            recycled=False,
            feed=None,
        ) -> typing.Iterable[objects.News]:

        if feed is not None and not isinstance(feed, objects.Feed):
            feed = self.get_feed(feed)

        wheres = []
        bindings = []

        if feed:
            feed_ids = [descendant.id for descendant in feed.walk_children()]
            wheres.append(f'feed_id IN {sqlhelpers.listify(feed_ids)}')

        if recycled is True:
            wheres.append('recycled == 1')
        elif recycled is False:
            wheres.append('recycled == 0')

        if read is True:
            wheres.append('read == 1')
        elif read is False:
            wheres.append('read == 0')
        if wheres:
            wheres = ' AND '.join(wheres)
            wheres = ' WHERE ' + wheres
        else:
            wheres = ''
        query = 'SELECT * FROM news' + wheres + ' ORDER BY published DESC'

        rows = self.select(query, bindings)
        for row in rows:
            yield self.get_cached_instance(objects.News, row)

    def get_newss_by_id(self, ids) -> typing.Iterable[objects.News]:
        return self.get_objects_by_id(objects.News, ids)

    def get_newss_by_sql(self, query, bindings=None) -> typing.Iterable[objects.News]:
        return self.get_objects_by_sql(objects.News, query, bindings)

    def _get_duplicate_news(self, feed, guid):
        if feed.isolate_guids:
            guid = f'_isolate_{feed.id}_{guid}'

        match = self.select_one('SELECT * FROM news WHERE rss_guid == ?', [guid])
        if match is None:
            return None

        return self.get_cached_instance(objects.News, match)

    def _ingest_one_news_atom(self, entry, feed):
        rss_guid = entry.id

        web_url = helpers.pick_web_url_atom(entry)

        updated = entry.updated
        if updated is not None:
            updated = updated.text
            updated = helpers.dateutil_parse(updated)
            updated = updated.timestamp()

        published = entry.published
        if published is not None:
            published = published.text
            published = helpers.dateutil_parse(published)
            published = published.timestamp()
        elif updated is not None:
            published = updated

        if updated is None and published is not None:
            updated = published

        title = entry.find('title')
        if title:
            title = title.text.strip()

        if rss_guid:
            rss_guid = rss_guid.text.strip()
        elif web_url:
            rss_guid = web_url
        elif title:
            rss_guid = title
        elif published:
            rss_guid = published

        if not rss_guid:
            raise exceptions.NoGUID(entry)

        duplicate = self._get_duplicate_news(feed=feed, guid=rss_guid)
        if duplicate:
            log.loud('Skipping duplicate feed=%s, guid=%s', feed.id, rss_guid)
            return BDBNewsMixin.DUPLICATE_BAIL

        text = entry.find('content')
        if text:
            text = text.text.strip()

        comments_url = None

        raw_authors = entry.find_all('author')
        authors = []
        for raw_author in raw_authors:
            author = {
                'name': raw_author.find('name'),
                'email': raw_author.find('email'),
                'uri': raw_author.find('uri'),
            }
            author = {key:(value.text if value else None) for (key, value) in author.items()}
            authors.append(author)

        raw_enclosures = entry.find_all('link', {'rel': 'enclosure'})
        enclosures = []
        for raw_enclosure in raw_enclosures:
            enclosure = {
                'type': raw_enclosure.get('type', None),
                'url': raw_enclosure.get('href', None),
                'size': raw_enclosure.get('length', None),
            }
            if enclosure.get('size') is not None:
                enclosure['size'] = int(enclosure['size'])

            enclosures.append(enclosure)

        news = self.add_news(
            authors=authors,
            comments_url=comments_url,
            enclosures=enclosures,
            feed=feed,
            published=published,
            rss_guid=rss_guid,
            text=text,
            title=title,
            updated=updated,
            web_url=web_url,
        )
        return news

    def _ingest_one_news_rss(self, item, feed):
        rss_guid = item.find('guid')

        title = item.find('title')
        if title:
            title = title.text.strip()

        text = item.find('description')
        if text:
            text = text.text.strip()

        web_url = item.find('link')
        if web_url:
            web_url = web_url.text.strip()
        elif rss_guid and rss_guid.get('isPermalink'):
            web_url = rss_guid.text

        if web_url and '://' not in web_url:
            web_url = None

        published = item.find('pubDate')
        if published:
            published = published.text
            published = helpers.dateutil_parse(published)
            published = published.timestamp()
        else:
            published = 0

        if rss_guid:
            rss_guid = rss_guid.text.strip()
        elif web_url:
            rss_guid = web_url
        elif title:
            rss_guid = f'{feed.id}_{title}'
        elif published:
            rss_guid = f'{feed.id}_{published}'

        if not rss_guid:
            raise exceptions.NoGUID(item)

        duplicate = self._get_duplicate_news(feed=feed, guid=rss_guid)
        if duplicate:
            log.loud('Skipping duplicate news, feed=%s, guid=%s', feed.id, rss_guid)
            return BDBNewsMixin.DUPLICATE_BAIL

        comments_url = item.find('comments')
        if comments_url is not None:
            comments_url = comments_url.text

        raw_authors = item.find_all('author')
        authors = []
        for raw_author in raw_authors:
            author = raw_author.text.strip()
            if author:
                author = {
                    'name': author,
                }
                authors.append(author)

        raw_enclosures = item.find_all('enclosure')
        enclosures = []
        for raw_enclosure in raw_enclosures:
            enclosure = {
                'type': raw_enclosure.get('type', None),
                'url': raw_enclosure.get('url', None),
                'size': raw_enclosure.get('length', None),
            }

            if enclosure.get('size') is not None:
                enclosure['size'] = int(enclosure['size'])

            enclosures.append(enclosure)

        news = self.add_news(
            authors=authors,
            comments_url=comments_url,
            enclosures=enclosures,
            feed=feed,
            published=published,
            rss_guid=rss_guid,
            text=text,
            title=title,
            updated=published,
            web_url=web_url,
        )
        return news

    def _ingest_news_atom(self, soup, feed):
        atom_feed = soup.find('feed')

        if not atom_feed:
            raise exceptions.BadXML('No feed element.')

        for entry in atom_feed.find_all('entry'):
            news = self._ingest_one_news_atom(entry, feed)
            if news is not BDBNewsMixin.DUPLICATE_BAIL:
                yield news

    def _ingest_news_rss(self, soup, feed):
        rss = soup.find('rss')

        # This won't happen under normal circumstances since Feed.refresh would
        # have raised already. But including these checks here in case user
        # calls directly.
        if not rss:
            raise exceptions.BadXML('No rss element.')

        channel = rss.find('channel')

        if not channel:
            raise exceptions.BadXML('No channel element.')

        for item in channel.find_all('item'):
            news = self._ingest_one_news_rss(item, feed)
            if news is not BDBNewsMixin.DUPLICATE_BAIL:
                yield news

    @worms.atomic
    def ingest_news_xml(self, soup:bs4.BeautifulSoup, feed):
        if soup.rss:
            newss = self._ingest_news_rss(soup, feed)
        elif soup.feed:
            newss = self._ingest_news_atom(soup, feed)
        else:
            raise exceptions.NeitherAtomNorRSS(soup)

        for news in newss:
            self.process_news_through_filters(news)

####################################################################################################

class BringDB(
        BDBFeedMixin,
        BDBFilterMixin,
        BDBNewsMixin,
        worms.DatabaseWithCaching,
    ):
    def __init__(
            self,
            data_directory=None,
            *,
            create=False,
            skip_version_check=False,
        ):
        '''
        data_directory:
            This directory will contain the sql file and anything else needed by
            the process. The directory is the database for all intents
            and purposes.

        create:
            If True, the data_directory will be created if it does not exist.
            If False, we expect that data_directory and the sql file exist.

        skip_version_check:
            Skip the version check so that you don't get DatabaseOutOfDate.
            Beware of modifying any data in this state.
        '''
        super().__init__()

        # DATA DIR PREP
        if data_directory is not None:
            pass
        else:
            data_directory = pathclass.cwd().with_child(constants.DEFAULT_DATADIR)

        if isinstance(data_directory, str):
            data_directory = helpers.remove_path_badchars(data_directory, allowed=':/\\')
        self.data_directory = pathclass.Path(data_directory)

        if self.data_directory.exists and not self.data_directory.is_dir:
            raise exceptions.BadDataDirectory(self.data_directory.absolute_path)

        # DATABASE / WORMS
        self._init_sql(create=create, skip_version_check=skip_version_check)

        # WORMS
        self.id_type = int
        self._init_column_index()
        self._init_caches()

    def _check_version(self):
        '''
        Compare database's user_version against constants.DATABASE_VERSION,
        raising exceptions.DatabaseOutOfDate if not correct.
        '''
        existing = self.pragma_read('user_version')
        if existing != constants.DATABASE_VERSION:
            raise exceptions.DatabaseOutOfDate(
                existing=existing,
                new=constants.DATABASE_VERSION,
                filepath=self.data_directory,
            )

    def _first_time_setup(self):
        log.info('Running first-time database setup.')
        with self.transaction:
            self._load_pragmas()
            self.pragma_write('user_version', constants.DATABASE_VERSION)
            self.executescript(constants.DB_INIT)

    def _init_caches(self):
        self.caches = {
            objects.Feed: cacheclass.Cache(maxlen=2000),
            objects.Filter: cacheclass.Cache(maxlen=1000),
            objects.News: cacheclass.Cache(maxlen=20000),
        }

    def _init_column_index(self):
        self.COLUMNS = constants.SQL_COLUMNS
        self.COLUMN_INDEX = constants.SQL_INDEX

    def _init_sql(self, create, skip_version_check):
        self.database_filepath = self.data_directory.with_child(constants.DEFAULT_DBNAME)
        existing_database = self.database_filepath.exists

        if not existing_database and not create:
            msg = f'"{self.database_filepath.absolute_path}" does not exist and create is off.'
            raise FileNotFoundError(msg)

        self.data_directory.makedirs(exist_ok=True)
        self.sql_read = self._make_sqlite_read_connection(self.database_filepath)
        self.sql_write = self._make_sqlite_write_connection(self.database_filepath)

        if existing_database:
            if not skip_version_check:
                self._check_version()
            with self.transaction:
                self._load_pragmas()
        else:
            self._first_time_setup()

    def _load_pragmas(self):
        log.debug('Reloading pragmas.')
        # 50 MB cache
        self.pragma_write('cache_size', -50000)
        self.pragma_write('foreign_keys', 'on')

    @classmethod
    def closest_bringdb(cls, path='.', *args, **kwargs):
        '''
        Starting from the given path and climbing upwards towards the filesystem
        root, look for an existing BringRSS data directory and return the
        BringDB object. If none exists, raise exceptions.NoClosestBringDB.
        '''
        path = pathclass.Path(path)
        starting = path

        while True:
            possible = path.with_child(constants.DEFAULT_DATADIR)
            if possible.is_dir:
                break
            parent = path.parent
            if path == parent:
                raise exceptions.NoClosestBringDB(starting.absolute_path)
            path = parent

        path = possible
        log.debug('Found closest BringDB at "%s".', path.absolute_path)
        bringdb = cls(
            data_directory=path,
            create=False,
            *args,
            **kwargs,
        )
        return bringdb

    def __del__(self):
        self.close()

    def __repr__(self):
        return f'BringDB(data_directory={self.data_directory})'

    def close(self) -> None:
        super().close()

    def generate_id(self, thing_class) -> int:
        '''
        Create a new ID number that is unique to the given table.
        '''
        if not issubclass(thing_class, objects.ObjectBase):
            raise TypeError(thing_class)

        table = thing_class.table

        while True:
            id = RNG.getrandbits(32)
            if not self.exists(f'SELECT 1 FROM {table} WHERE id == ?', [id]):
                return id
