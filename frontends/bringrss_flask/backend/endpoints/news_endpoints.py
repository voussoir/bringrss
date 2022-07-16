import flask; from flask import request

from voussoirkit import flasktools
from voussoirkit import stringtools

from .. import common

import bringrss

site = common.site

####################################################################################################

@site.route('/news/<news_id>/set_read', methods=['POST'])
@flasktools.required_fields(['read'], forbid_whitespace=True)
def post_news_set_read(news_id):
    news = common.get_news(news_id, response_type='json')
    read = stringtools.truthystring(request.form['read'])
    with common.bringdb.transaction:
        news.set_read(read)
    return flasktools.json_response(news.jsonify())

@site.route('/news/<news_id>/set_recycled', methods=['POST'])
@flasktools.required_fields(['recycled'], forbid_whitespace=True)
def post_news_set_recycled(news_id):
    news = common.get_news(news_id, response_type='json')
    recycled = stringtools.truthystring(request.form['recycled'])
    with common.bringdb.transaction:
        news.set_recycled(recycled)
    return flasktools.json_response(news.jsonify())

@site.route('/news/<news_id>.json', methods=['GET'])
def get_news(news_id):
    news = common.get_news(news_id, response_type='json')
    return flasktools.json_response(news.jsonify(complete=True))

@site.route('/news/<news_id>.json', methods=['POST'])
def post_get_news(news_id):
    news = common.get_news(news_id, response_type='json')
    mark_read = request.form.get('set_read', None)
    mark_read = stringtools.truthystring(mark_read)
    if mark_read is not None:
        with common.bringdb.transaction:
            news.set_read(mark_read)
    return flasktools.json_response(news.jsonify(complete=True))

@site.route('/batch/news/set_read', methods=['POST'])
@flasktools.required_fields(['news_ids', 'read'], forbid_whitespace=True)
def post_batch_set_read():
    news_ids = request.form['news_ids']
    news_ids = stringtools.comma_space_split(news_ids)
    news_ids = [int(id) for id in news_ids]
    newss = common.get_newss(news_ids, response_type='json')

    read = stringtools.truthystring(request.form['read'])

    return_ids = []
    with common.bringdb.transaction:
        for news in newss:
            news.set_read(read)
            return_ids.append(news.id)

    return flasktools.json_response(return_ids)

@site.route('/batch/news/set_recycled', methods=['POST'])
@flasktools.required_fields(['news_ids', 'recycled'], forbid_whitespace=True)
def post_batch_recycle_news():
    news_ids = request.form['news_ids']
    news_ids = stringtools.comma_space_split(news_ids)
    news_ids = [int(id) for id in news_ids]
    newss = common.get_newss(news_ids, response_type='json')

    recycled = stringtools.truthystring(request.form['recycled'])

    return_ids = []
    with common.bringdb.transaction:
        for news in newss:
            news.set_recycled(recycled)
            return_ids.append(news.id)

    return flasktools.json_response(return_ids)
