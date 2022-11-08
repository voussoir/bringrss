const api = {};

/**************************************************************************************************/
api.feeds = {};

api.feeds.add_feed =
function add_feed(rss_url, title, isolate_guids, callback)
{
    return http.post({
        url: "/feeds/add",
        data: {"rss_url": rss_url, "title": title, "isolate_guids": isolate_guids},
        callback: callback,
    });
}

api.feeds.delete =
function delete_feed(feed_id, callback)
{
    return http.post({
        url: `/feed/${feed_id}/delete`,
        callback: callback,
    });
}

api.feeds.get_feeds =
function get_feeds(callback)
{
    return http.get({
        url: "/feeds.json",
        callback: callback,
    });
}

api.feeds.refresh =
function refresh(feed_id, callback)
{
    return http.post({
        url: `/feed/${feed_id}/refresh`,
        callback: callback,
    });
}

api.feeds.refresh_all =
function refresh_all(callback)
{
    return http.post({
        url: "/feeds/refresh_all",
        callback: callback,
    });
}

api.feeds.set_autorefresh_interval =
function set_autorefresh_interval(feed_id, interval, callback)
{
    return http.post({
        url: `/feed/${feed_id}/set_autorefresh_interval`,
        data: {"autorefresh_interval": interval},
        callback: callback,
    });
}

api.feeds.set_filters =
function set_filters(feed_id, filter_ids, callback)
{
    return http.post({
        url: `/feed/${feed_id}/set_filters`,
        data: {"filter_ids": filter_ids.join(",")},
        callback: callback,
    });
}

api.feeds.set_http_headers =
function set_http_headers(feed_id, http_headers, callback)
{
    return http.post({
        url: `/feed/${feed_id}/set_http_headers`,
        data: {"http_headers": http_headers},
        callback: callback,
    });
}

api.feeds.set_icon =
function set_icon(feed_id, image_base64, callback)
{
    return http.post({
        url: `/feed/${feed_id}/set_icon`,
        data: {"image_base64": image_base64},
        callback: callback,
    });
}

api.feeds.set_isolate_guids =
function set_isolate_guids(feed_id, isolate_guids, callback)
{
    return http.post({
        url: `/feed/${feed_id}/set_isolate_guids`,
        data: {"isolate_guids": isolate_guids},
        callback: callback,
    });
}

api.feeds.set_parent =
function set_parent(feed_id, parent_id, ui_order_rank, callback)
{
    data = {"parent_id": parent_id};
    if (ui_order_rank !== null)
    {
        data["ui_order_rank"] = ui_order_rank;
    }
    return http.post({
        url: `/feed/${feed_id}/set_parent`,
        data: data,
        callback: callback,
    });
}

api.feeds.set_refresh_with_others =
function set_refresh_with_others(feed_id, refresh_with_others, callback)
{
    return http.post({
        url: `/feed/${feed_id}/set_refresh_with_others`,
        data: {"refresh_with_others": refresh_with_others},
        callback: callback,
    });
}

api.feeds.set_rss_url =
function set_rss_url(feed_id, rss_url, callback)
{
    return http.post({
        url: `/feed/${feed_id}/set_rss_url`,
        data: {"rss_url": rss_url},
        callback: callback,
    });
}

api.feeds.set_web_url =
function set_web_url(feed_id, web_url, callback)
{
    return http.post({
        url: `/feed/${feed_id}/set_web_url`,
        data: {"web_url": web_url},
        callback: callback,
    });
}

api.feeds.set_title =
function set_title(feed_id, title, callback)
{
    return http.post({
        url: `/feed/${feed_id}/set_title`,
        data: {"title": title},
        callback: callback,
    });
}

api.feeds.set_ui_order_rank =
function set_ui_order_rank(feed_id, ui_order_rank, callback)
{
    return http.post({
        url: `/feed/${feed_id}/set_ui_order_rank`,
        data: {"ui_order_rank": ui_order_rank},
        callback: callback,
    });
}

/**************************************************************************************************/
api.filters = {};

api.filters.add_filter =
function add_filter(name, conditions, actions, callback)
{
    return http.post({
        url: "/filters/add",
        data: {"name": name, "conditions": conditions, "actions": actions},
        callback: callback,
    });
}

api.filters.delete_filter =
function delete_filter(filter_id, callback)
{
    return http.post({
        url: `/filter/${filter_id}/delete`,
        callback: callback,
    });
}

api.filters.get_filters =
function get_filters(callback)
{
    return http.get({
        url: "/filters.json",
        callback: callback,
    });
}

api.filters.run_filter_now =
function run_filter_now(filter_id, feed_id, callback)
{
    const data = {};
    if (feed_id !== null)
    {
        data['feed_id'] = feed_id;
    }
    return http.post({
        url: `/filter/${filter_id}/run_filter`,
        data: data,
        callback: callback,
    });
}

api.filters.set_actions =
function set_actions(filter_id, actions, callback)
{
    return http.post({
        url: `/filter/${filter_id}/set_actions`,
        data: {"actions": actions},
        callback: callback,
    });
}

api.filters.set_conditions =
function set_conditions(filter_id, conditions, callback)
{
    return http.post({
        url: `/filter/${filter_id}/set_conditions`,
        data: {"conditions": conditions},
        callback: callback,
    });
}

api.filters.set_name =
function set_name(filter_id, name, callback)
{
    return http.post({
        url: `/filter/${filter_id}/set_name`,
        data: {"name": name},
        callback: callback,
    });
}

api.filters.update_filter =
function update_filter(filter_id, name, conditions, actions, callback)
{
    return http.post({
        url: `/filter/${filter_id}/update`,
        data: {"name": name, "conditions": conditions, "actions": actions},
        callback: callback,
    });
}

/**************************************************************************************************/
api.news = {};

api.news.get_and_set_read =
function get_and_set_read(news_id, callback)
{
    return http.post({
        url: `/news/${news_id}.json`,
        data: {"set_read": true},
        callback: callback,
    });
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
    return http.get({
        url: url,
        callback: callback, callback,
    });

}

api.news.set_read =
function set_read(news_id, read, callback)
{
    return http.post({
        url: `/news/${news_id}/set_read`,
        data: {"read": read},
        callback: callback,
    });
}

api.news.set_recycled =
function set_recycled(news_id, recycled, callback)
{
    return http.post({
        url: `/news/${news_id}/set_recycled`,
        data: {"recycled": recycled},
        callback: callback,
    });
}

api.news.batch_set_read =
function batch_set_read(news_ids, read, callback)
{
    return http.post({
        url: `/batch/news/set_read`,
        data: {"news_ids": news_ids.join(","), "read": read},
        callback: callback,
    });
}

api.news.batch_set_recycled =
function batch_set_recycled(news_ids, recycled, callback)
{
    return http.post({
        url: `/batch/news/set_recycled`,
        data: {"news_ids": news_ids.join(","), "recycled": recycled},
        callback: callback,
    });
}
