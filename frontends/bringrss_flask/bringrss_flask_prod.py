'''
This file is the WSGI entrypoint for remote / production use.

If you are using Gunicorn, for example:
gunicorn bringrss_flask_prod:site --bind "0.0.0.0:PORT" --access-logfile "-"
'''
import werkzeug.middleware.proxy_fix
import os

from voussoirkit import pipeable

from bringrss_flask import backend

backend.site.wsgi_app = werkzeug.middleware.proxy_fix.ProxyFix(backend.site.wsgi_app)

site = backend.site
site.debug = False

if os.environ.get('BRINGRSS_DEMO_MODE', False):
    pipeable.stderr('Setting demo_mode = True')
    site.demo_mode = True

backend.common.init_bringdb()
backend.common.start_background_threads()
