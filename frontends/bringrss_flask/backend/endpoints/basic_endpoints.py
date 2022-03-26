import flask; from flask import request

from voussoirkit import flasktools
from voussoirkit import stringtools
from voussoirkit import vlogging

log = vlogging.get_logger(__name__)

from .. import common

import bringrss

site = common.site

####################################################################################################

@site.route('/favicon.ico')
@site.route('/favicon.png')
def favicon():
    return flask.send_file(common.FAVICON_PATH.absolute_path)

@site.route('/news.json')
@site.route('/feed/<feed_id>/news.json')
@flasktools.cached_endpoint(max_age=0, etag_function=lambda: common.bringdb.last_commit_id, max_urls=200)
def get_newss_json(feed_id=None):
    if feed_id is None:
        feed = None
    else:
        feed = common.get_feed(feed_id, response_type='json')
    read = stringtools.truthystring(request.args.get('read', False))
    recycled = stringtools.truthystring(request.args.get('recycled', False))
    newss = common.bringdb.get_newss(feed=feed, read=read, recycled=recycled)
    response = [news.jsonify() for news in newss]
    return flasktools.json_response(response)

@site.route('/')
@site.route('/feed/<feed_id>')
def get_newss(feed_id=None):
    if feed_id is None:
        feed = None
    else:
        feed = common.get_feed(feed_id, response_type='html')

    return common.render_template(
        request,
        'root.html',
        specific_feed=feed,
    )

@site.route('/about')
def get_about():
    return common.render_template(request, 'about.html')

@site.route('/sse')
def get_sse():
    response = flask.Response(flasktools.sse_generator(), mimetype='text/event-stream')
    # Skip gzip
    response.direct_passthrough = True
    return response
