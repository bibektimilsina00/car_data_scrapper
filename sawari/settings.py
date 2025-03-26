BOT_NAME = "sawari"

SPIDER_MODULES = ["sawari.spiders"]
NEWSPIDER_MODULE = "sawari.spiders"


ROBOTSTXT_OBEY = False

# Crawl responsibly
CONCURRENT_REQUESTS = 8
DOWNLOAD_DELAY = 1

RANDOMIZE_DOWNLOAD_DELAY = True
# Retry settings
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]

# Cache settings
HTTPCACHE_ENABLED = True
HTTPCACHE_EXPIRATION_SECS = 86400  # 24 hours

# Custom settings for car details spider
CAR_DETAILS_SETTINGS = {
    "DOWNLOAD_DELAY": 2,
    "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
}


TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
