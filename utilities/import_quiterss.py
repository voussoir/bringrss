import base64
import argparse
import os
import sqlite3
import textwrap
import sys

from voussoirkit import betterhelp
from voussoirkit import pipeable
from voussoirkit import vlogging
from voussoirkit import interactive
from voussoirkit import niceprints

import bringrss

log = vlogging.getLogger(__name__, 'import_quiterss')

def import_quiterss_argparse(args):
    if not os.path.isfile(args.feedsdb):
        pipeable.stderr(f'{args.feedsdb} is not a file.')
        return 1

    bringdb = bringrss.bringdb.BringDB.closest_bringdb()
    message = textwrap.dedent('''
    You should make a backup of your BringRSS database before doing this.
    Do not perform this import more than once. We will not search for duplicate data.
    If you need to try the import again, restore from your backup first.

    Only feeds and news are imported. Filters are not. Sorry for the inconvenience.
    ''').strip()

    pipeable.stderr()
    pipeable.stderr(niceprints.in_box(message, title='Importing from QuiteRSS'))

    if not interactive.getpermission('Are you ready?'):
        return 1

    with bringdb.transaction:
        import_quiterss(feedsdb, bringdb)

    return 0

def import_quiterss(feedsdb, bringdb):
    quite_sql = sqlite3.connect(feedsdb)
    quite_sql.row_factory = sqlite3.Row
    feed_id_map = {}
    query = '''
    SELECT
        id,
        text,
        description,
        xmlUrl,
        htmlUrl,
        image,
        parentId,
        rowToParent,
        updateIntervalEnable,
        updateInterval,
        updateIntervalType,
        disableUpdate
    FROM feeds;
    '''
    feeds = list(quite_sql.execute(query))
    while feeds:
        feed = feeds.pop(0)
        quite_id = feed['id']
        if feed['parentId'] == 0:
            parent = None
        elif feed['parentId'] in feed_id_map:
            parent = feed_id_map[feed['parentId']]
        else:
            # The parent is probably somewhere else in the list, let's come
            # back to it later.
            feeds.append(feed)
            continue

        title = feed['text']
        description = feed['description']
        rss_url = feed['xmlUrl']
        web_url = feed['htmlUrl']
        # rowToParent is zero-indexed, we use 1-index.
        if parent:
            # If the parent has ui_order_rank of 8, then a child with rowToParent
            # of 4 will be 8.0004 and everything will get reassigned later.
            ui_order_rank = parent.ui_order_rank + ((feed['rowToParent'] + 1) / 10000)
        else:
            ui_order_rank = feed['rowToParent'] + 1

        if feed['updateIntervalEnable'] == 1 and feed['updateInterval'] > 0:
            if feed['updateIntervalType'] in {1, "1"}:
                # hours
                autorefresh_interval = feed['updateInterval'] * 3600
            elif feed['updateIntervalType'] in {0, "0"}:
                # minutes
                autorefresh_interval = feed['updateInterval'] * 60
            elif feed['updateIntervalType'] in {-1, "-1"}:
                # seconds
                autorefresh_interval = feed['updateInterval']
        else:
            autorefresh_interval = 0

        if feed['disableUpdate'] == 1:
            refresh_with_others = False
            autorefresh_interval = min(autorefresh_interval, -1 * autorefresh_interval)
        else:
            refresh_with_others = True

        isolate_guids = False

        if feed['image']:
            icon = base64.b64decode(feed['image'])
        else:
            icon = None

        feed = bringdb.add_feed(
            autorefresh_interval=autorefresh_interval,
            description=description,
            icon=icon,
            isolate_guids=isolate_guids,
            parent=parent,
            refresh_with_others=refresh_with_others,
            rss_url=rss_url,
            title=title,
            ui_order_rank=ui_order_rank,
            web_url=web_url,
        )
        feed_id_map[quite_id] = feed

    bringdb.reassign_ui_order_ranks()

    query = '''
    SELECT
        feedId,
        guid,
        description,
        title,
        published,
        modified,
        author_name,
        author_uri,
        author_email,
        read,
        comments,
        enclosure_length,
        enclosure_type,
        enclosure_url,
        link_href
    FROM news
    WHERE deleted == 0;
    '''
    newss = list(quite_sql.execute(query))
    for news in newss:
        quite_read = news['read']

        authors = [{
            'name': news['author_name'],
            'email': news['author_email'],
            'uri': news['author_uri'],
        }]
        enclosures = [{
            'url': news['enclosure_url'],
            'type': news['enclosure_type'],
            'size': int(news['enclosure_length']) if news.get('enclosure_length') else None
        }]

        news = bringdb.add_news(
            authors=authors,
            comments_url=news['comments'],
            enclosures=enclosures,
            feed=feed_id_map[news['feedId']],
            published=news['published'],
            rss_guid=news['guid'],
            text=news['description'],
            title=news['title'],
            updated=news['modified'] or news['published'],
            web_url=news['link_href'],
        )
        if quite_read > 0:
            news.set_read(True)

@vlogging.main_decorator
def main(argv):
    parser = argparse.ArgumentParser(
        description='''
        Import feeds and news from QuiteRSS to BringRSS.
        ''',
    )
    parser.add_argument(
        'feedsdb',
        help='''
        Filepath to the feeds.db in your QuiteRSS folder.
        ''',
    )
    parser.set_defaults(func=import_quiterss_argparse)

    return betterhelp.go(parser, argv)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
