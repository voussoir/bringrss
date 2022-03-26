const api = {};

/**************************************************************************************************/
api.feeds = {};

api.feeds.add_feed =
function add_feed(rss_url, title, isolate_guids, callback)
{
    const url = "/feeds/add";
    const data = {"rss_url": rss_url, "title": title, "isolate_guids": isolate_guids};
    return common.post(url, data, callback);
}

api.feeds.delete =
function delete_feed(feed_id, callback)
{
    const url = `/feed/${feed_id}/delete`;
    return common.post(url, null, callback);
}

api.feeds.get_feeds =
function get_feeds(callback)
{
    const url = "/feeds.json";
    return common.get(url, callback);
}

api.feeds.refresh =
function refresh(feed_id, callback)
{
    const url = `/feed/${feed_id}/refresh`;
    return common.post(url, null, callback);
}

api.feeds.refresh_all =
function refresh_all(callback)
{
    const url = "/feeds/refresh_all";
    return common.post(url, null, callback);
}

api.feeds.set_autorefresh_interval =
function set_autorefresh_interval(feed_id, interval, callback)
{
    const url = `/feed/${feed_id}/set_autorefresh_interval`;
    const data = {"autorefresh_interval": interval};
    return common.post(url, data, callback);
}

api.feeds.set_filters =
function set_filters(feed_id, filter_ids, callback)
{
    const url = `/feed/${feed_id}/set_filters`;
    const data = {"filter_ids": filter_ids.join(",")};
    return common.post(url, data, callback);
}

api.feeds.set_http_headers =
function set_http_headers(feed_id, http_headers, callback)
{
    const url = `/feed/${feed_id}/set_http_headers`;
    const data = {"http_headers": http_headers};
    return common.post(url, data, callback);
}

api.feeds.set_icon =
function set_icon(feed_id, image_base64, callback)
{
    const url = `/feed/${feed_id}/set_icon`;
    const data = {"image_base64": image_base64};
    return common.post(url, data, callback);
}

api.feeds.set_isolate_guids =
function set_isolate_guids(feed_id, isolate_guids, callback)
{
    const url = `/feed/${feed_id}/set_isolate_guids`;
    const data = {"isolate_guids": isolate_guids};
    return common.post(url, data, callback);
}

api.feeds.set_parent =
function set_parent(feed_id, parent_id, ui_order_rank, callback)
{
    const url = `/feed/${feed_id}/set_parent`;
    const data = {"parent_id": parent_id};
    if (ui_order_rank !== null)
    {
        data["ui_order_rank"] = ui_order_rank;
    }
    return common.post(url, data, callback);
}

api.feeds.set_refresh_with_others =
function set_refresh_with_others(feed_id, refresh_with_others, callback)
{
    const url = `/feed/${feed_id}/set_refresh_with_others`;
    const data = {"refresh_with_others": refresh_with_others};
    return common.post(url, data, callback);
}

api.feeds.set_rss_url =
function set_rss_url(feed_id, rss_url, callback)
{
    const url = `/feed/${feed_id}/set_rss_url`;
    const data = {"rss_url": rss_url};
    return common.post(url, data, callback);
}

api.feeds.set_web_url =
function set_web_url(feed_id, web_url, callback)
{
    const url = `/feed/${feed_id}/set_web_url`;
    const data = {"web_url": web_url};
    return common.post(url, data, callback);
}

api.feeds.set_title =
function set_title(feed_id, title, callback)
{
    const url = `/feed/${feed_id}/set_title`;
    const data = {"title": title};
    return common.post(url, data, callback);
}

api.feeds.set_ui_order_rank =
function set_ui_order_rank(feed_id, ui_order_rank, callback)
{
    const url = `/feed/${feed_id}/set_ui_order_rank`;
    const data = {"ui_order_rank": ui_order_rank};
    return common.post(url, data, callback);
}

/**************************************************************************************************/
api.filters = {};

api.filters.add_filter =
function add_filter(name, conditions, actions, callback)
{
    const url = "/filters/add";
    const data = {"name": name, "conditions": conditions, "actions": actions};
    return common.post(url, data, callback);
}

api.filters.delete_filter =
function delete_filter(filter_id, callback)
{
    const url = `/filter/${filter_id}/delete`;
    return common.post(url, null, callback);
}

api.filters.get_filters =
function get_filters(callback)
{
    const url = "/filters.json";
    return common.get(url, callback);
}

api.filters.run_filter_now =
function run_filter_now(filter_id, feed_id, callback)
{
    const url = `/filter/${filter_id}/run_filter`;
    const data = {};
    if (feed_id !== null)
    {
        data['feed_id'] = feed_id;
    }
    return common.post(url, data, callback);
}

api.filters.set_actions =
function set_actions(filter_id, actions, callback)
{
    const url = `/filter/${filter_id}/set_actions`;
    const data = {"actions": actions};
    return common.post(url, data, callback);
}

api.filters.set_conditions =
function set_conditions(filter_id, conditions, callback)
{
    const url = `/filter/${filter_id}/set_conditions`;
    const data = {"conditions": conditions};
    return common.post(url, data, callback);
}

api.filters.set_name =
function set_name(filter_id, name, callback)
{
    const url = `/filter/${filter_id}/set_name`;
    const data = {"name": name};
    return common.post(url, data, callback);
}

api.filters.update_filter =
function update_filter(filter_id, name, conditions, actions, callback)
{
    const url = `/filter/${filter_id}/update`;
    const data = {"name": name, "conditions": conditions, "actions": actions};
    return common.post(url, data, callback);
}

/**************************************************************************************************/
api.news = {};

api.news.get_and_set_read =
function get_and_set_read(news_id, callback)
{
    const url = `/news/${news_id}.json`;
    const data = {"set_read": true};
    return common.post(url, data, callback);
}

api.news.get_newss =
function get_newss(feed_id, read, recycled, callback)
{
    let parameters = new URLSearchParams();
    if (read !== null)
    {
        parameters.set("read", read);
    }
    if (recycled !== null)
    {
        parameters.set("recycled", recycled);
    }
    parameters = parameters.toString();
    if (parameters !== "")
    {
        parameters = "?" + parameters;
    }
    let url = (feed_id === null) ? "/news.json" : `/feed/${feed_id}/news.json`;
    url += parameters;
    return common.get(url, callback);

}

api.news.set_read =
function set_read(news_id, read, callback)
{
    const url = `/news/${news_id}/set_read`;
    const data = {"read": read};
    return common.post(url, data, callback);
}

api.news.set_recycled =
function set_recycled(news_id, recycled, callback)
{
    const url = `/news/${news_id}/set_recycled`;
    const data = {"recycled": recycled};
    return common.post(url, data, callback);
}

api.news.batch_set_read =
function batch_set_read(news_ids, read, callback)
{
    const url = `/batch/news/set_read`;
    const data = {"news_ids": news_ids.join(","), "read": read};
    return common.post(url, data, callback);
}

api.news.batch_set_recycled =
function batch_set_recycled(news_ids, recycled, callback)
{
    const url = `/batch/news/set_recycled`;
    const data = {"news_ids": news_ids.join(","), "recycled": recycled};
    return common.post(url, data, callback);
}
