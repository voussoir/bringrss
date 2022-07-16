import argparse
import sys

from voussoirkit import betterhelp
from voussoirkit import hms
from voussoirkit import operatornotify
from voussoirkit import pipeable
from voussoirkit import vlogging

import bringrss

log = vlogging.getLogger(__name__, 'bringrss')

bringdb = None
def load_bringdb():
    global bringdb
    if bringdb is not None:
        return
    bringdb = bringrss.bringdb.BringDB.closest_bringdb()

####################################################################################################

def init_argparse(args):
    bringdb = bringrss.bringdb.BringDB(create=True)
    return 0

def refresh_argparse(args):
    load_bringdb()
    now = bringrss.helpers.now()
    soonest = float('inf')
    with bringdb.transaction:
        for feed in list(bringdb.get_feeds()):
            next_refresh = feed.next_refresh
            if now > next_refresh:
                feed.refresh()
            elif next_refresh < soonest:
                soonest = next_refresh
    if soonest != float('inf'):
        soonest = hms.seconds_to_hms_letters(soonest - now)
        pipeable.stderr(f'The next soonest is in {soonest}.')
    return 0

def refresh_all_argparse(args):
    load_bringdb()
    with bringdb.transaction:
        for feed in list(bringdb.get_feeds()):
            feed.refresh()

@operatornotify.main_decorator(subject='bringrss_cli')
@vlogging.main_decorator
def main(argv):
    parser = argparse.ArgumentParser(
        description='''
        This is the command-line interface for BringRSS, so that you can automate
        your database and integrated it into other scripts.
        ''',
    )

    subparsers = parser.add_subparsers()

    p_init = subparsers.add_parser(
        'init',
        description='''
        Create a new BringRSS database in the current directory.
        ''',
    )
    p_init.set_defaults(func=init_argparse)

    p_refresh = subparsers.add_parser(
        'refresh',
        description='''
        Refresh feeds if their autorefresh interval has elapsed since their
        last refresh.
        ''',
    )
    p_refresh.set_defaults(func=refresh_argparse)

    p_refresh_all = subparsers.add_parser(
        'refresh_all',
        aliases=['refresh-all'],
        description='''
        Refresh all feeds now.
        ''',
    )
    p_refresh_all.set_defaults(func=refresh_all_argparse)

    return betterhelp.go(parser, argv)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
