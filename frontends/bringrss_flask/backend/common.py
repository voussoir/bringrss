'''
Do not execute this file directly.
Use bringrss_flask_dev.py or bringrss_flask_prod.py.
'''
import flask; from flask import request
import functools
import json
import queue
import threading
import time
import traceback

from voussoirkit import flasktools
from voussoirkit import pathclass
from voussoirkit import sentinel
from voussoirkit import vlogging

log = vlogging.get_logger(__name__)

import bringrss

from . import jinja_filters

# Flask init #######################################################################################

# __file__ = .../bringrss_flask/backend/common.py
# root_dir = .../bringrss_flask
root_dir = pathclass.Path(__file__).parent.parent

TEMPLATE_DIR = root_dir.with_child('templates')
STATIC_DIR = root_dir.with_child('static')
FAVICON_PATH = STATIC_DIR.with_child('favicon.png')
BROWSER_CACHE_DURATION = 180

site = flask.Flask(
    __name__,
    template_folder=TEMPLATE_DIR.absolute_path,
    static_folder=STATIC_DIR.absolute_path,
)
site.config.update(
    SEND_FILE_MAX_AGE_DEFAULT=BROWSER_CACHE_DURATION,
    TEMPLATES_AUTO_RELOAD=True,
)
site.jinja_env.add_extension('jinja2.ext.do')
site.jinja_env.globals['INF'] = float('inf')
site.jinja_env.trim_blocks = True
site.jinja_env.lstrip_blocks = True
jinja_filters.register_all(site)
site.localhost_only = False
site.demo_mode = False

# Response wrappers ################################################################################

def catch_bringrss_exception(endpoint):
    '''
    If an bringrssException is raised, automatically catch it and convert it
    into a json response so that the user doesn't receive error 500.
    '''
    @functools.wraps(endpoint)
    def wrapped(*args, **kwargs):
        try:
            return endpoint(*args, **kwargs)
        except bringrss.exceptions.BringException as exc:
            if isinstance(exc, bringrss.exceptions.NoSuch):
                status = 404
            else:
                status = 400
            response = flasktools.json_response(exc.jsonify(), status=status)
            flask.abort(response)
    return wrapped

@site.before_request
def before_request():
    # Note for prod: If you see that remote_addr is always 127.0.0.1 for all
    # visitors, make sure your reverse proxy is properly setting X-Forwarded-For
    # so that werkzeug's proxyfix can set that as the remote_addr.
    # In NGINX: proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    request.is_localhost = (request.remote_addr == '127.0.0.1')
    if site.localhost_only and not request.is_localhost:
        flask.abort(403)

@site.after_request
def after_request(response):
    response = flasktools.gzip_response(request, response)
    return response

site.route = flasktools.decorate_and_route(
    flask_app=site,
    decorators=[
        flasktools.ensure_response_type,
        functools.partial(
            flasktools.give_theme_cookie,
            cookie_name='bringrss_theme',
            default_theme='slate',
        ),
        catch_bringrss_exception,
    ],
)

# Get functions ####################################################################################

def getter_wrapper(getter_function):
    def getter_wrapped(thing_id, response_type):
        if response_type not in {'html', 'json'}:
            raise TypeError(f'response_type should be html or json, not {response_type}.')

        try:
            return getter_function(thing_id)

        except bringrss.exceptions.BringException as exc:
            if isinstance(exc, bringrss.exceptions.NoSuch):
                status = 404
            else:
                status = 400

            if response_type == 'html':
                flask.abort(status, exc.error_message)
            else:
                response = exc.jsonify()
                response = flasktools.json_response(response, status=status)
                flask.abort(response)

        except Exception as exc:
            traceback.print_exc()
            if response_type == 'html':
                flask.abort(500)
            else:
                flask.abort(flasktools.json_response({}, status=500))

    return getter_wrapped

@getter_wrapper
def get_feed(feed_id):
    return bringdb.get_feed(feed_id)

@getter_wrapper
def get_feeds(feed_ids):
    return bringdb.get_feeds_by_id(feed_ids)

@getter_wrapper
def get_filter(filter_id):
    return bringdb.get_filter(filter_id)

@getter_wrapper
def get_filters(filter_ids):
    return bringdb.get_filters_by_id(filter_ids)

@getter_wrapper
def get_news(news_id):
    return bringdb.get_news(news_id)

@getter_wrapper
def get_newss(news_ids):
    return bringdb.get_newss_by_id(news_ids)

# Other functions ##################################################################################

def back_url():
    return request.args.get('goto') or request.referrer or '/'

def render_template(request, template_name, **kwargs):
    theme = request.cookies.get('bringrss_theme', None)

    response = flask.render_template(
        template_name,
        site=site,
        request=request,
        theme=theme,
        **kwargs,
    )
    return response

# Background threads ###############################################################################

# This item can be put in a thread's message queue, and when the thread notices
# it, the thread will quit gracefully.
QUIT_EVENT = sentinel.Sentinel('quit')

####################################################################################################

AUTOREFRESH_THREAD_EVENTS = queue.Queue()

def autorefresh_thread():
    '''
    This thread keeps an eye on the last_refresh and autorefresh_interval of all
    the feeds, and puts the feeds into the REFRESH_QUEUE when they are ready.

    When a feed is refreshed manually, we recalculate the schedule so it does
    not autorefresh until another interval has elapsed.
    '''
    log.info('Starting autorefresh thread.')
    while True:
        if not REFRESH_QUEUE.empty():
            time.sleep(10)
            continue
        now = bringrss.helpers.now()
        soonest = now + 3600
        for feed in list(bringdb.get_feeds()):
            next_refresh = feed.next_refresh
            if now > next_refresh:
                add_feed_to_refresh_queue(feed)
                # If the refresh fails it'll try again in an hour, if it
                # succeeds it'll be one interval. We'll know for sure later but
                # this is when this auto thread will check and see.
                next_refresh = now + feed.autorefresh_interval

            soonest = min(soonest, next_refresh)

        now = bringrss.helpers.now()
        sleepy = soonest - now
        sleepy = max(sleepy, 30)
        sleepy = min(sleepy, 7200)
        sleepy = int(sleepy)
        log.info(f'Sleeping {sleepy} until next refresh.')
        try:
            event = AUTOREFRESH_THREAD_EVENTS.get(timeout=sleepy)
            if event is QUIT_EVENT:
                break
        except queue.Empty:
            pass

####################################################################################################

REFRESH_QUEUE = queue.Queue()
# The Queue objects cannot be iterated and do not support membership testing.
# We use this set to prevent the same feed being queued up for refresh twice
# at the same time.
_REFRESH_QUEUE_SET = set()

def refresh_queue_thread():
    '''
    This thread handles all Feed refreshing and sends the results out via the
    SSE channel. Whether the refresh was user-initiated by clicking on the
    "Refresh" / "Refresh all" button, or server-initiated by the autorefresh
    timer, all actual refreshing happens through here. This allows us to make
    sure we only have one refresh going on at a time and clients don't have to
    distinguish between responses to their refresh request and server-initiated
    refreshes, they can just always watch the SSE.
    '''
    def _refresh_one(feed):
        if not feed.rss_url:
            feed.clear_last_refresh_error()
            return

        # Don't bother calculating unreads
        flasktools.send_sse(
            event='feed_refresh_started',
            data=json.dumps(feed.jsonify(unread_count=False)),
        )
        try:
            feed.refresh()
        except Exception as exc:
            log.warning('Refreshing %s encountered:\n%s', feed, traceback.format_exc())
        bringdb.commit()
        flasktools.send_sse(
            event='feed_refresh_finished',
            data=json.dumps(feed.jsonify(unread_count=True)),
        )

    log.info('Starting refresh_queue thread.')
    while True:
        feed = REFRESH_QUEUE.get()
        if feed is QUIT_EVENT:
            break
        _refresh_one(feed)
        _REFRESH_QUEUE_SET.discard(feed)
        if REFRESH_QUEUE.empty():
            flasktools.send_sse(event='feed_refresh_queue_finished', data='')
            _REFRESH_QUEUE_SET.clear()

def add_feed_to_refresh_queue(feed):
    if site.demo_mode:
        return

    if feed in _REFRESH_QUEUE_SET:
        return

    log.debug('Adding %s to refresh queue.', feed)
    REFRESH_QUEUE.put(feed)
    _REFRESH_QUEUE_SET.add(feed)

def clear_refresh_queue():
    while not REFRESH_QUEUE.empty():
        feed = REFRESH_QUEUE.get_nowait()
    _REFRESH_QUEUE_SET.clear()

def sse_keepalive_thread():
    log.info('Starting SSE keepalive thread.')
    while True:
        flasktools.send_sse(event='keepalive', data=bringrss.helpers.now())
        time.sleep(60)

####################################################################################################

# These functions will be called by the launcher, flask_dev, flask_prod.

def init_bringdb(*args, **kwargs):
    global bringdb
    bringdb = bringrss.bringdb.BringDB.closest_bringdb(*args, **kwargs)
    if site.demo_mode:
        do_nothing = lambda *args, **kwargs: None
        for module in [bringrss.bringdb, bringrss.objects]:
            classes = [cls for (name, cls) in vars(module).items() if isinstance(cls, type)]
            for cls in classes:
                for (name, attribute) in vars(cls).items():
                    if getattr(attribute, 'is_worms_transaction', False) is True:
                        setattr(cls, name, do_nothing)
                        print(cls, name, 'DO NOTHING')

        bringdb.commit = do_nothing
        bringdb.insert = do_nothing
        bringdb.update = do_nothing
        bringdb.delete = do_nothing
        AUTOREFRESH_THREAD_EVENTS.put(QUIT_EVENT)
        AUTOREFRESH_THREAD_EVENTS.put = do_nothing

        REFRESH_QUEUE.put(QUIT_EVENT)

def start_background_threads():
    threading.Thread(target=autorefresh_thread, daemon=True).start()
    threading.Thread(target=refresh_queue_thread, daemon=True).start()
    threading.Thread(target=sse_keepalive_thread, daemon=True).start()
