import bs4
import datetime
import dateutil.parser
import importlib
import sys

from . import constants

from voussoirkit import cacheclass
from voussoirkit import httperrors
from voussoirkit import pathclass
from voussoirkit import vlogging

log = vlogging.get_logger(__name__)

_xml_etag_cache = cacheclass.Cache(maxlen=100)

def dateutil_parse(string):
    return dateutil.parser.parse(string, tzinfos=constants.DATEUTIL_TZINFOS)

def fetch_xml(url, headers={}) -> bs4.BeautifulSoup:
    log.debug('Fetching %s.', url)
    response = constants.http_session.get(url, headers=headers)
    httperrors.raise_for_status(response)
    soup = bs4.BeautifulSoup(response.text, 'xml')
    return soup

def fetch_xml_cached(url, headers={}) -> bs4.BeautifulSoup:
    '''
    Fetch the RSS / Atom feed, using a local cache to take advantage of HTTP304
    responses.
    '''
    cached = _xml_etag_cache.get(url)
    if cached and cached['request_headers'] == headers:
        headers = headers.copy()
        headers['if-none-match'] = cached['etag']

    # To do: use expires / cache-control to avoid making the request at all.
    log.debug('Fetching %s.', url)
    response = constants.http_session.get(url, headers=headers)
    httperrors.raise_for_status(response)

    if cached and response.status_code == 304:
        # Consider: after returning the cached text, it will still go through
        # the rest of the xml parsing and news ingesting steps even though it
        # will almost certainly add nothing new. But I say almost certainly
        # because you could have changed feed settings like isolate_guids.
        # May be room for optimization but it's not worth creating weird edge
        # cases over.
        log.debug('304 Using cached XML for %s.', url)
        response_text = cached['text']
    else:
        response_text = response.text
        if response.headers.get('etag'):
            cached = {
                'request_headers': headers,
                'etag': response.headers['etag'],
                'text': response_text,
            }
            _xml_etag_cache[url] = cached

    soup = bs4.BeautifulSoup(response_text, 'xml')
    return soup

def import_module_by_path(path):
    '''
    Raises pathclass.NotFile if file does not exist.
    Raises ValueError if basename cannot be a Python identifier.
    '''
    given_path = path
    path = pathclass.Path(path)
    path.assert_is_file()
    name = path.basename.split('.', 1)[0]
    if not name.isidentifier():
        raise ValueError(given_path)
    _syspath = sys.path
    _sysmodules = sys.modules.copy()
    sys.path = [path.parent.absolute_path]
    module = importlib.import_module(name)
    sys.path = _syspath
    sys.modules = _sysmodules
    return module

@staticmethod
def normalize_int_or_none(x):
    if x is None:
        return None

    if isinstance(x, int):
        return x

    if isinstance(x, float):
        return int(x)

    raise TypeError(f'{x} should be int or None, not {type(x)}.')

@staticmethod
def normalize_string_blank_to_none(string):
    if string is None:
        return None

    if not isinstance(string, str):
        raise TypeError(string)

    string = string.strip()
    if not string:
        return None

    return string

@staticmethod
def normalize_string_strip(string):
    if not isinstance(string, str):
        raise TypeError(string)

    return string.strip()

@staticmethod
def normalize_string_not_blank(string):
    if not isinstance(string, str):
        raise TypeError(string)

    string = string.strip()
    if not string:
        raise ValueError(string)

    return string

def now(timestamp=True):
    '''
    Return the current UTC timestamp or datetime object.
    '''
    n = datetime.datetime.now(datetime.timezone.utc)
    if timestamp:
        return n.timestamp()
    return n

def pick_web_url_atom(entry:bs4.BeautifulSoup):
    best_web_url = entry.find('link', {'rel': 'alternate', 'type': 'text/html'}, recursive=False)
    if best_web_url:
        return best_web_url['href']

    alternate_url = entry.find('link', {'rel': 'alternate'}, recursive=False)
    if alternate_url:
        return alternate_url['href']

    link = entry.find('link', recursive=False)
    if link:
        return link['href']

    return None

def xml_is_atom(soup:bs4.BeautifulSoup):
    if soup.find('feed'):
        return True

    return False

def xml_is_rss(soup:bs4.BeautifulSoup):
    if soup.find('rss') and soup.find('rss').find('channel'):
        return True

    return False
