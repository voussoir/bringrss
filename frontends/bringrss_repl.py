import argparse
import code
import sys
import traceback

from voussoirkit import interactive
from voussoirkit import pipeable
from voussoirkit import vlogging

import bringrss

def bringrepl_argparse(args):
    global B

    try:
        B = bringrss.bringdb.BringDB.closest_bringdb()
    except bringrss.exceptions.NoClosestBringDB as exc:
        pipeable.stderr(exc.error_message)
        pipeable.stderr('Try `bringrss_cli.py init` to create the database.')
        return 1

    if args.exec_statement:
        with B.transaction():
            exec(args.exec_statement)
    else:
        while True:
            try:
                code.interact(banner='', local=dict(globals(), **locals()))
            except SystemExit:
                pass
            if len(B.savepoints) == 0:
                break
            print('You have uncommited changes, are you sure you want to quit?')
            if interactive.getpermission():
                break

@vlogging.main_decorator
def main(argv):
    parser = argparse.ArgumentParser()

    parser.add_argument('--exec', dest='exec_statement', default=None)
    parser.set_defaults(func=bringrepl_argparse)

    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
