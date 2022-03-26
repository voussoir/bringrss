import base64
import flask; from flask import request
import traceback

from voussoirkit import stringtools
from voussoirkit import flasktools
from voussoirkit import vlogging

log = vlogging.get_logger(__name__)

from .. import common

import bringrss

site = common.site

# Feed listings ####################################################################################

@site.route('/feeds.json')
@flasktools.cached_endpoint(max_age=0, etag_function=lambda: common.bringdb.last_commit_id)
def get_feeds_json():
    feeds = common.bringdb.get_feeds()
    response = []
    unread_counts = common.bringdb.get_bulk_unread_counts()
    for feed in feeds:
        j = feed.jsonify()
        j['unread_count'] = unread_counts.get(feed, 0)
        response.append(j)
    return flasktools.json_response(response)

@site.route('/feeds/add', methods=['POST'])
def post_feeds_add():
    rss_url = request.form.get('rss_url')
    title = request.form.get('title')
    isolate_guids = request.form.get('isolate_guids', False)
    isolate_guids = stringtools.truthystring(isolate_guids)
    feed = common.bringdb.add_feed(rss_url=rss_url, title=title, isolate_guids=isolate_guids)

    # We want to refresh the feed now and not just put it on the refresh queue,
    # because when the user gets the response to this endpoint they will
    # navigate to the /settings, and we want to have that page pre-populated
    # with the title and icon. If the feed goes to the refresh queue, the page
    # will come up blank, then get populated in the background, which is bad
    # ux. However, we need to commit first, because if the refresh fails we want
    # the user to be able to see the Feed in the ui and read its
    # last_refresh_error message.
    common.bringdb.commit()
    try:
        feed.refresh()
        common.bringdb.commit()
    except Exception:
        log.warning('Refreshing %s raised:\n%s', feed, traceback.format_exc())

    return flasktools.json_response(feed.jsonify())

@site.route('/feeds/refresh_all', methods=['POST'])
def post_feeds_refresh_all():
    predicate = lambda feed: feed.refresh_with_others
    # The root feeds are not exempt from the predicate because the user clicked
    # the refresh all button, not the root feed specifically.
    root_feeds = [root for root in common.bringdb.get_root_feeds() if predicate(root)]
    for root_feed in root_feeds:
        for feed in root_feed.walk_children(predicate=predicate, yield_self=True):
            common.add_feed_to_refresh_queue(feed)
    return flasktools.json_response({})

# Individual feeds #################################################################################

@site.route('/feed/<feed_id>.json')
def get_feed_json(feed_id):
    feed = common.get_feed(feed_id, response_type='json')
    return flasktools.json_response(feed.jsonify())

@site.route('/feed/<feed_id>/delete', methods=['POST'])
def post_feed_delete(feed_id):
    feed = common.get_feed(feed_id, response_type='json')
    feed.delete()
    common.bringdb.commit()
    return flasktools.json_response({})

@site.route('/feed/<feed_id>/icon.png')
def get_feed_icon(feed_id):
    feed = common.get_feed(feed_id, response_type='html')

    if feed.icon:
        headers = {'Cache-Control': f'max-age={common.BROWSER_CACHE_DURATION}'}
        return flask.Response(feed.icon, mimetype='image/png', headers=headers)
    elif feed.rss_url:
        basic = common.STATIC_DIR.with_child('basic_icons').with_child('rss.png')
        return flask.send_file(basic.absolute_path)
    else:
        basic = common.STATIC_DIR.with_child('basic_icons').with_child('folder.png')
        return flask.send_file(basic.absolute_path)

@site.route('/feed/<feed_id>/refresh', methods=['POST'])
def post_feed_refresh(feed_id):
    feed = common.get_feed(feed_id, response_type='json')

    predicate = lambda child: child.refresh_with_others
    # We definitely want to refresh this feed regardless of the predicate,
    # because that's what was requested.
    feeds = list(feed.walk_children(predicate=predicate, yield_self=True))
    for feed in feeds:
        common.add_feed_to_refresh_queue(feed)

    return flasktools.json_response({})

@site.route('/feed/<feed_id>/settings')
def get_feed_settings(feed_id):
    feed = common.get_feed(feed_id, response_type='html')
    feed_filters = list(feed.get_filters())
    available_filters = set(common.bringdb.get_filters())
    available_filters.difference_update(feed_filters)
    return common.render_template(
        request,
        'feed_settings.html',
        feed=feed,
        feed_filters=feed_filters,
        available_filters=available_filters,
    )

@site.route('/feed/<feed_id>/set_autorefresh_interval', methods=['POST'])
@flasktools.required_fields(['autorefresh_interval'])
def post_feed_set_autorefresh_interval(feed_id):
    feed = common.get_feed(feed_id, response_type='json')
    autorefresh_interval = request.form['autorefresh_interval']
    try:
        autorefresh_interval = int(autorefresh_interval)
    except ValueError:
        return flasktools.json_response({}, status=400)

    if autorefresh_interval != feed.autorefresh_interval:
        feed.set_autorefresh_interval(autorefresh_interval)
        common.bringdb.commit()
        # Wake up the autorefresh thread so it can recalculate its schedule.
        common.AUTOREFRESH_THREAD_EVENTS.put("wake up!")
    return flasktools.json_response(feed.jsonify())

@site.route('/feed/<feed_id>/set_filters', methods=['POST'])
@flasktools.required_fields(['filter_ids'])
def post_feed_set_filters(feed_id):
    feed = common.get_feed(feed_id, response_type='json')
    filter_ids = stringtools.comma_space_split(request.form['filter_ids'])
    filters = [common.get_filter(id, response_type='json') for id in filter_ids]
    feed.set_filters(filters)
    common.bringdb.commit()
    return flasktools.json_response(feed.jsonify(filters=True))

@site.route('/feed/<feed_id>/set_http_headers', methods=['POST'])
@flasktools.required_fields(['http_headers'])
def post_feed_set_http_headers(feed_id):
    feed = common.get_feed(feed_id, response_type='json')
    feed.set_http_headers(request.form['http_headers'])
    common.bringdb.commit()
    return flasktools.json_response(feed.jsonify())

@site.route('/feed/<feed_id>/set_icon', methods=['POST'])
@flasktools.required_fields(['image_base64'])
def post_feed_set_icon(feed_id):
    feed = common.get_feed(feed_id, response_type='json')
    image_base64 = request.form['image_base64']
    image_base64 = image_base64.split(';base64,')[-1]
    image_binary = base64.b64decode(image_base64)
    feed.set_icon(image_binary)
    common.bringdb.commit()
    return flasktools.json_response(feed.jsonify())

@site.route('/feed/<feed_id>/set_isolate_guids', methods=['POST'])
@flasktools.required_fields(['isolate_guids'])
def post_feed_set_isolate_guids(feed_id):
    feed = common.get_feed(feed_id, response_type='json')
    try:
        isolate_guids = stringtools.truthystring(request.form['isolate_guids'])
    except ValueError:
        return flasktools.json_response({}, status=400)
    feed.set_isolate_guids(isolate_guids)
    common.bringdb.commit()
    return flasktools.json_response(feed.jsonify())

@site.route('/feed/<feed_id>/set_parent', methods=['POST'])
@flasktools.required_fields(['parent_id'])
def post_feed_set_parent(feed_id):
    feed = common.get_feed(feed_id, response_type='json')

    parent_id = request.form['parent_id']
    if parent_id == '':
        parent = None
    else:
        parent = common.get_feed(parent_id, response_type='json')

    ui_order_rank = request.form.get('ui_order_rank', None)
    if ui_order_rank is not None:
        ui_order_rank = float(ui_order_rank)

    if parent != feed.parent or ui_order_rank != feed.ui_order_rank:
        feed.set_parent(parent, ui_order_rank=ui_order_rank)
        common.bringdb.commit()

    return flasktools.json_response(feed.jsonify())

@site.route('/feed/<feed_id>/set_refresh_with_others', methods=['POST'])
@flasktools.required_fields(['refresh_with_others'])
def post_feed_set_refresh_with_others(feed_id):
    feed = common.get_feed(feed_id, response_type='json')
    refresh_with_others = stringtools.truthystring(request.form['refresh_with_others'])
    if refresh_with_others != feed.refresh_with_others:
        feed.set_refresh_with_others(refresh_with_others)
        common.bringdb.commit()
    return flasktools.json_response(feed.jsonify())

@site.route('/feed/<feed_id>/set_rss_url', methods=['POST'])
@flasktools.required_fields(['rss_url'])
def post_feed_set_rss_url(feed_id):
    feed = common.get_feed(feed_id, response_type='json')
    rss_url = request.form['rss_url']
    if rss_url != feed.rss_url:
        feed.set_rss_url(rss_url)
        common.bringdb.commit()
    return flasktools.json_response(feed.jsonify())

@site.route('/feed/<feed_id>/set_web_url', methods=['POST'])
@flasktools.required_fields(['web_url'])
def post_feed_set_web_url(feed_id):
    feed = common.get_feed(feed_id, response_type='json')
    web_url = request.form['web_url']
    if web_url != feed.web_url:
        feed.set_web_url(web_url)
        common.bringdb.commit()
    return flasktools.json_response(feed.jsonify())

@site.route('/feed/<feed_id>/set_title', methods=['POST'])
@flasktools.required_fields(['title'])
def post_feed_set_title(feed_id):
    feed = common.get_feed(feed_id, response_type='json')
    title = request.form['title']
    if title != feed.title:
        feed.set_title(title)
        common.bringdb.commit()
    return flasktools.json_response(feed.jsonify())

@site.route('/feed/<feed_id>/set_ui_order_rank', methods=['POST'])
@flasktools.required_fields(['ui_order_rank'], forbid_whitespace=True)
def post_feed_set_ui_order_rank(feed_id):
    feed = common.get_feed(feed_id, response_type='json')
    ui_order_rank = float(request.form['ui_order_rank'])
    if ui_order_rank != feed.ui_order_rank:
        feed.set_ui_order_rank(ui_order_rank)
        common.bringdb.reassign_ui_order_rank()
        common.bringdb.commit()
    return flasktools.json_response(feed.jsonify())
