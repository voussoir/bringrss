import requests

from voussoirkit import sqlhelpers

DATABASE_VERSION = 1
DB_VERSION_PRAGMA = f'''
PRAGMA user_version = {DATABASE_VERSION};
'''

DB_PRAGMAS = f'''
-- 50 MB cache
PRAGMA cache_size = -50000;
PRAGMA foreign_keys = ON;
'''

DB_INIT = f'''
BEGIN;
{DB_PRAGMAS}
{DB_VERSION_PRAGMA}
----------------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feeds(
    id INT PRIMARY KEY NOT NULL,
    parent_id INT,
    rss_url TEXT,
    web_url TEXT,
    title TEXT,
    description TEXT,
    created INT,
    refresh_with_others INT NOT NULL,
    last_refresh INT NOT NULL,
    last_refresh_attempt INT NOT NULL,
    last_refresh_error TEXT,
    autorefresh_interval INT NOT NULL,
    http_headers TEXT,
    isolate_guids INT NOT NULL,
    icon BLOB,
    ui_order_rank INT
);
CREATE INDEX IF NOT EXISTS index_feeds_id on feeds(id);
----------------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS filters(
    id INT PRIMARY KEY NOT NULL,
    name TEXT,
    created INT,
    conditions TEXT NOT NULL,
    actions TEXT NOT NULL
);
----------------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS news(
    id INT PRIMARY KEY NOT NULL,
    feed_id INT NOT NULL,
    original_feed_id INT NOT NULL,
    rss_guid TEXT NOT NULL,
    published INT,
    updated INT,
    title TEXT,
    text TEXT,
    web_url TEXT,
    comments_url TEXT,
    created INT,
    read INT NOT NULL,
    recycled INT NOT NULL,
    -- The authors and enclosures are stored as a JSON list of dicts. Normally I
    -- don't like to store JSON in my databases, but I'm really not interested
    -- in breaking this out in a many-to-many table to achieve proper normal
    -- form. The quantity of enclosures is probably going to be low enough, disk
    -- space is cheap enough, and for the time being we have no SQL queries
    -- against the enclosure fields to justify a perf difference.
    authors TEXT,
    enclosures TEXT,
    FOREIGN KEY(feed_id) REFERENCES feeds(id)
);
CREATE INDEX IF NOT EXISTS index_news_id on news(id);
CREATE INDEX IF NOT EXISTS index_news_feed_id on news(feed_id);

-- Not used very often, but when you switch a feed's isolate_guids setting on
-- and off, we need to rewrite the rss_guid for all news items from that feed,
-- so having an index there really helps.
CREATE INDEX IF NOT EXISTS index_news_original_feed_id on news(original_feed_id);

-- This will be the most commonly used search index. We search for news that is
-- not read or recycled, ordered by published desc, and belongs to one of
-- several feeds (feed or folder of feeds).
CREATE INDEX IF NOT EXISTS index_news_recycled_read_published_feed_id on news(recycled, read, published, feed_id);

-- Less common but same idea. Finding read + unread news that's not recycled,
-- published desc, from your feed or folder.
CREATE INDEX IF NOT EXISTS index_news_recycled_published_feed_id on news(recycled, published, feed_id);

-- Used to figure out which incoming news is new and which already exist.
CREATE INDEX IF NOT EXISTS index_news_guid on news(rss_guid);
----------------------------------------------------------------------------------------------------

----------------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feed_filter_rel(
    feed_id INT NOT NULL,
    filter_id INT NOT NULL,
    order_rank INT NOT NULL,
    FOREIGN KEY(feed_id) REFERENCES feeds(id),
    FOREIGN KEY(filter_id) REFERENCES filters(id),
    PRIMARY KEY(feed_id, filter_id)
);
----------------------------------------------------------------------------------------------------
COMMIT;
'''
SQL_COLUMNS = sqlhelpers.extract_table_column_map(DB_INIT)
SQL_INDEX = sqlhelpers.reverse_table_column_map(SQL_COLUMNS)

DEFAULT_DATADIR = '_bringrss'
DEFAULT_DBNAME = 'bringrss.db'

# Normally I don't even put version numbers on my projects, but since we're
# making requests to third parties its fair for them to know in case our HTTP
# behavior changes.
VERSION = '0.0.1'
http_session = requests.Session()
http_session.headers['User-Agent'] = f'voussoir/BringRSS v{VERSION}'

# Thank you h-j-13
# https://stackoverflow.com/a/54629675/5430534
DATEUTIL_TZINFOS = {
    'A': 1 * 3600,
    'ACDT': 10.5 * 3600,
    'ACST': 9.5 * 3600,
    'ACT': -5 * 3600,
    'ACWST': 8.75 * 3600,
    'ADT': 4 * 3600,
    'AEDT': 11 * 3600,
    'AEST': 10 * 3600,
    'AET': 10 * 3600,
    'AFT': 4.5 * 3600,
    'AKDT': -8 * 3600,
    'AKST': -9 * 3600,
    'ALMT': 6 * 3600,
    'AMST': -3 * 3600,
    'AMT': -4 * 3600,
    'ANAST': 12 * 3600,
    'ANAT': 12 * 3600,
    'AQTT': 5 * 3600,
    'ART': -3 * 3600,
    'AST': 3 * 3600,
    'AT': -4 * 3600,
    'AWDT': 9 * 3600,
    'AWST': 8 * 3600,
    'AZOST': 0 * 3600,
    'AZOT': -1 * 3600,
    'AZST': 5 * 3600,
    'AZT': 4 * 3600,
    'AoE': -12 * 3600,
    'B': 2 * 3600,
    'BNT': 8 * 3600,
    'BOT': -4 * 3600,
    'BRST': -2 * 3600,
    'BRT': -3 * 3600,
    'BST': 6 * 3600,
    'BTT': 6 * 3600,
    'C': 3 * 3600,
    'CAST': 8 * 3600,
    'CAT': 2 * 3600,
    'CCT': 6.5 * 3600,
    'CDT': -5 * 3600,
    'CEST': 2 * 3600,
    'CET': 1 * 3600,
    'CHADT': 13.75 * 3600,
    'CHAST': 12.75 * 3600,
    'CHOST': 9 * 3600,
    'CHOT': 8 * 3600,
    'CHUT': 10 * 3600,
    'CIDST': -4 * 3600,
    'CIST': -5 * 3600,
    'CKT': -10 * 3600,
    'CLST': -3 * 3600,
    'CLT': -4 * 3600,
    'COT': -5 * 3600,
    'CST': -6 * 3600,
    'CT': -6 * 3600,
    'CVT': -1 * 3600,
    'CXT': 7 * 3600,
    'ChST': 10 * 3600,
    'D': 4 * 3600,
    'DAVT': 7 * 3600,
    'DDUT': 10 * 3600,
    'E': 5 * 3600,
    'EASST': -5 * 3600,
    'EAST': -6 * 3600,
    'EAT': 3 * 3600,
    'ECT': -5 * 3600,
    'EDT': -4 * 3600,
    'EEST': 3 * 3600,
    'EET': 2 * 3600,
    'EGST': 0 * 3600,
    'EGT': -1 * 3600,
    'EST': -5 * 3600,
    'ET': -5 * 3600,
    'F': 6 * 3600,
    'FET': 3 * 3600,
    'FJST': 13 * 3600,
    'FJT': 12 * 3600,
    'FKST': -3 * 3600,
    'FKT': -4 * 3600,
    'FNT': -2 * 3600,
    'G': 7 * 3600,
    'GALT': -6 * 3600,
    'GAMT': -9 * 3600,
    'GET': 4 * 3600,
    'GFT': -3 * 3600,
    'GILT': 12 * 3600,
    'GMT': 0 * 3600,
    'GST': 4 * 3600,
    'GYT': -4 * 3600,
    'H': 8 * 3600,
    'HDT': -9 * 3600,
    'HKT': 8 * 3600,
    'HOVST': 8 * 3600,
    'HOVT': 7 * 3600,
    'HST': -10 * 3600,
    'I': 9 * 3600,
    'ICT': 7 * 3600,
    'IDT': 3 * 3600,
    'IOT': 6 * 3600,
    'IRDT': 4.5 * 3600,
    'IRKST': 9 * 3600,
    'IRKT': 8 * 3600,
    'IRST': 3.5 * 3600,
    'IST': 5.5 * 3600,
    'JST': 9 * 3600,
    'K': 10 * 3600,
    'KGT': 6 * 3600,
    'KOST': 11 * 3600,
    'KRAST': 8 * 3600,
    'KRAT': 7 * 3600,
    'KST': 9 * 3600,
    'KUYT': 4 * 3600,
    'L': 11 * 3600,
    'LHDT': 11 * 3600,
    'LHST': 10.5 * 3600,
    'LINT': 14 * 3600,
    'M': 12 * 3600,
    'MAGST': 12 * 3600,
    'MAGT': 11 * 3600,
    'MART': 9.5 * 3600,
    'MAWT': 5 * 3600,
    'MDT': -6 * 3600,
    'MHT': 12 * 3600,
    'MMT': 6.5 * 3600,
    'MSD': 4 * 3600,
    'MSK': 3 * 3600,
    'MST': -7 * 3600,
    'MT': -7 * 3600,
    'MUT': 4 * 3600,
    'MVT': 5 * 3600,
    'MYT': 8 * 3600,
    'N': -1 * 3600,
    'NCT': 11 * 3600,
    'NDT': 2.5 * 3600,
    'NFT': 11 * 3600,
    'NOVST': 7 * 3600,
    'NOVT': 7 * 3600,
    'NPT': 5.5 * 3600,
    'NRT': 12 * 3600,
    'NST': 3.5 * 3600,
    'NUT': -11 * 3600,
    'NZDT': 13 * 3600,
    'NZST': 12 * 3600,
    'O': -2 * 3600,
    'OMSST': 7 * 3600,
    'OMST': 6 * 3600,
    'ORAT': 5 * 3600,
    'P': -3 * 3600,
    'PDT': -7 * 3600,
    'PET': -5 * 3600,
    'PETST': 12 * 3600,
    'PETT': 12 * 3600,
    'PGT': 10 * 3600,
    'PHOT': 13 * 3600,
    'PHT': 8 * 3600,
    'PKT': 5 * 3600,
    'PMDT': -2 * 3600,
    'PMST': -3 * 3600,
    'PONT': 11 * 3600,
    'PST': -8 * 3600,
    'PT': -8 * 3600,
    'PWT': 9 * 3600,
    'PYST': -3 * 3600,
    'PYT': -4 * 3600,
    'Q': -4 * 3600,
    'QYZT': 6 * 3600,
    'R': -5 * 3600,
    'RET': 4 * 3600,
    'ROTT': -3 * 3600,
    'S': -6 * 3600,
    'SAKT': 11 * 3600,
    'SAMT': 4 * 3600,
    'SAST': 2 * 3600,
    'SBT': 11 * 3600,
    'SCT': 4 * 3600,
    'SGT': 8 * 3600,
    'SRET': 11 * 3600,
    'SRT': -3 * 3600,
    'SST': -11 * 3600,
    'SYOT': 3 * 3600,
    'T': -7 * 3600,
    'TAHT': -10 * 3600,
    'TFT': 5 * 3600,
    'TJT': 5 * 3600,
    'TKT': 13 * 3600,
    'TLT': 9 * 3600,
    'TMT': 5 * 3600,
    'TOST': 14 * 3600,
    'TOT': 13 * 3600,
    'TRT': 3 * 3600,
    'TVT': 12 * 3600,
    'U': -8 * 3600,
    'ULAST': 9 * 3600,
    'ULAT': 8 * 3600,
    'UTC': 0 * 3600,
    'UYST': -2 * 3600,
    'UYT': -3 * 3600,
    'UZT': 5 * 3600,
    'V': -9 * 3600,
    'VET': -4 * 3600,
    'VLAST': 11 * 3600,
    'VLAT': 10 * 3600,
    'VOST': 6 * 3600,
    'VUT': 11 * 3600,
    'W': -10 * 3600,
    'WAKT': 12 * 3600,
    'WARST': -3 * 3600,
    'WAST': 2 * 3600,
    'WAT': 1 * 3600,
    'WEST': 1 * 3600,
    'WET': 0 * 3600,
    'WFT': 12 * 3600,
    'WGST': -2 * 3600,
    'WGT': -3 * 3600,
    'WIB': 7 * 3600,
    'WIT': 9 * 3600,
    'WITA': 8 * 3600,
    'WST': 14 * 3600,
    'WT': 0 * 3600,
    'X': -11 * 3600,
    'Y': -12 * 3600,
    'YAKST': 10 * 3600,
    'YAKT': 9 * 3600,
    'YAPT': 10 * 3600,
    'YEKST': 6 * 3600,
    'YEKT': 5 * 3600,
    'Z': 0 * 3600,
}
