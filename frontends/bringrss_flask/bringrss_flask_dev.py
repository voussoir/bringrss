'''
This file is the launcher for local / development use.
'''
import argparse
import os
import sys
import werkzeug.serving
werkzeug.serving._log_add_style = False

from voussoirkit import betterhelp
from voussoirkit import flasktools
from voussoirkit import operatornotify
from voussoirkit import pathclass
from voussoirkit import vlogging

log = vlogging.getLogger(__name__, 'bringrss_flask_dev')

import bringrss
import backend

site = backend.site
site.debug = True

####################################################################################################

def bringrss_flask_dev(
        *,
        demo_mode,
        localhost_only,
        init,
        port,
    ):
    if localhost_only:
        log.info('Setting localhost_only = True')
        site.localhost_only = True

    if demo_mode:
        log.info('Setting demo_mode = True')
        site.demo_mode = True

    if init:
        bringrss.bringdb.BringDB(create=True)

    try:
        backend.common.init_bringdb()
    except bringrss.exceptions.NoClosestBringDB as exc:
        log.error(exc.error_message)
        log.error('Try adding --init to create the database.')
        return 1

    message = f'Starting server on port {port}, pid={os.getpid()}.'
    log.info(message)

    backend.common.start_background_threads()

    try:
        site.run(
            host='0.0.0.0',
            port=port,
            threaded=True,
            debug=True,
            use_reloader=False,
            request_handler=flasktools.MyWSGIRequestHandler,
        )
        return 0
    except KeyboardInterrupt:
        log.info('Goodbye')

def bringrss_flask_dev_argparse(args):
    return bringrss_flask_dev(
        demo_mode=args.demo_mode,
        localhost_only=args.localhost_only,
        init=args.init,
        port=args.port,
    )

@operatornotify.main_decorator(subject='bringrss_flask_dev', notify_every_line=True)
@vlogging.main_decorator(log=log)
def main(argv):
    parser = argparse.ArgumentParser(
        description='''
        This file is the gevent launcher for local / development use.
        ''',
    )
    parser.add_argument(
        'port',
        nargs='?',
        type=int,
        default=27464,
        help='''
        Port number on which to run the server.
        ''',
    )
    parser.add_argument(
        '--demo_mode',
        '--demo-mode',
        action='store_true',
        help='''
        If this flag is passed, the server operates in demo mode, which means
        absolutely nothing can make modifications to the database and it is safe
        to present to the world.
        ''',
    )
    parser.add_argument(
        '--init',
        action='store_true',
        help='''
        Create a new BringRSS database in the current folder. If this is your
        first time running the server, you should include this.
        ''',
    )
    parser.add_argument(
        '--localhost_only',
        '--localhost-only',
        action='store_true',
        help='''
        If this flag is passed, only localhost will be able to access the server.
        Other users on the LAN will be blocked.
        ''',
    )
    parser.set_defaults(func=bringrss_flask_dev_argparse)

    return betterhelp.go(parser, argv)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
