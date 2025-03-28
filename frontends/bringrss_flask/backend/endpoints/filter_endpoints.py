import flask; from flask import request
import traceback

from voussoirkit import flasktools
from voussoirkit import vlogging

log = vlogging.get_logger(__name__)

from .. import common

import bringrss

site = common.site

####################################################################################################

@site.route('/filters.json')
@flasktools.cached_endpoint(max_age=0, etag_function=lambda: common.bringdb.last_commit_id)
def get_filters_json():
    filters = common.bringdb.get_filters()
    filters = sorted(filters, key=lambda filt: filt.display_name.lower())
    response = [filt.jsonify() for filt in filters]
    return flasktools.json_response(response)

@site.route('/filters')
def get_filters():
    filters = common.bringdb.get_filters()
    filters = sorted(filters, key=lambda filt: filt.display_name.lower())
    return common.render_template(
        request,
        'filters.html',
        filters=filters,
        filter_class=bringrss.objects.Filter,
        specific_filter=None,
    )

@site.route('/filters/add', methods=['POST'])
@flasktools.required_fields(['conditions', 'actions'], forbid_whitespace=True)
def post_filters_add():
    name = request.form.get('name', None)
    conditions = request.form['conditions']
    actions = request.form['actions']
    with common.bringdb.transaction:
        filt = common.bringdb.add_filter(name=name, conditions=conditions, actions=actions)
    flasktools.send_sse(event='filters_changed', data=None)
    return flasktools.json_response(filt.jsonify())

@site.route('/filter/<filter_id>')
def get_filter(filter_id):
    filt = common.get_filter(filter_id, response_type='html')
    filters = [filt]
    return common.render_template(
        request,
        'filters.html',
        filters=filters,
        filter_class=bringrss.objects.Filter,
        specific_filter=filt.id,
    )

@site.route('/filter/<filter_id>.json')
def get_filter_json(filter_id):
    filt = common.get_filter(filter_id, response_type='json')
    return flasktools.json_response(filt.jsonify())

@site.route('/filter/<filter_id>/delete', methods=['POST'])
def post_filter_delete(filter_id):
    filt = common.get_filter(filter_id, response_type='json')
    with common.bringdb.transaction:
        try:
            filt.delete()
        except bringrss.exceptions.FilterStillInUse as exc:
            return flasktools.json_response(exc.jsonify(), status=400)
    flasktools.send_sse(event='filters_changed', data=None)
    return flasktools.json_response({})

@site.route('/filter/<filter_id>/run_filter', methods=['POST'])
def post_run_filter_now(filter_id):
    feed_id = request.form.get('feed_id')
    if feed_id:
        feed = common.get_feed(feed_id, response_type='json')
    else:
        feed = None

    try:
        with common.bringdb.transaction:
            filt = common.get_filter(filter_id, response_type='json')
            newss = list(common.bringdb.get_newss(
                feed=feed,
                read=None,
                recycled=None,
            ))
            log.info('Running %s.', filt)
            for news in newss:
                filt.process_news(news)
    except Exception as exc:
        log.warning('Running %s raised:\n%s', filt, traceback.format_exc())

    return flasktools.json_response({})

@site.route('/filter/<filter_id>/set_actions', methods=['POST'])
@flasktools.required_fields(['actions'], forbid_whitespace=True)
def post_filter_set_actions(filter_id):
    filt = common.get_filter(filter_id, response_type='json')
    actions = request.form['actions']
    if actions != filt.actions:
        with common.bringdb.transaction:
            filt.set_actions(actions)
    return flasktools.json_response(filt.jsonify())

@site.route('/filter/<filter_id>/set_conditions', methods=['POST'])
@flasktools.required_fields(['conditions'], forbid_whitespace=True)
def post_filter_set_conditions(filter_id):
    filt = common.get_filter(filter_id, response_type='json')
    conditions = request.form['conditions']
    if conditions != filt.conditions:
        with common.bringdb.transaction:
            filt.set_conditions(conditions)
    return flasktools.json_response(filt.jsonify())

@site.route('/filter/<filter_id>/set_name', methods=['POST'])
@flasktools.required_fields(['name'])
def post_filter_set_name(filter_id):
    filt = common.get_filter(filter_id, response_type='json')
    name = request.form['name']
    if name != filt.name:
        with common.bringdb.transaction:
            filt.set_name(name)
    return flasktools.json_response(filt.jsonify())

@site.route('/filter/<filter_id>/update', methods=['POST'])
def post_filter_update(filter_id):
    filt = common.get_filter(filter_id, response_type='json')
    name = request.form.get('name', None)

    with common.bringdb.transaction:
        if name is not None:
            filt.set_name(name)

        conditions = request.form.get('conditions', None)
        if conditions is not None:
            filt.set_conditions(conditions)

        actions = request.form.get('actions', None)
        if actions is not None:
            filt.set_actions(actions)

    flasktools.send_sse(event='filters_changed', data=None)
    return flasktools.json_response(filt.jsonify())
