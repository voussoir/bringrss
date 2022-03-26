import datetime
import jinja2.filters

####################################################################################################

filter_functions = []
global_functions = []

def filter_function(function):
    filter_functions.append(function)
    return function

def global_function(function):
    global_functions.append(function)
    return function

def register_all(site):
    for function in filter_functions:
        site.jinja_env.filters[function.__name__] = function

    for function in global_functions:
        site.jinja_env.globals[function.__name__] = function

####################################################################################################

@filter_function
def http_headers_dict_to_lines(http_headers):
    if not http_headers:
        return ''
    lines = '\n'.join(f'{key}: {value}' for (key, value) in sorted(http_headers.items()))
    return lines

@filter_function
def timestamp_to_8601(timestamp):
    return datetime.datetime.utcfromtimestamp(timestamp).isoformat(' ') + ' UTC'

@filter_function
def timestamp_to_8601_local(timestamp):
    return datetime.datetime.fromtimestamp(timestamp).isoformat(' ')

@filter_function
def timestamp_to_string(timestamp, format):
    date = datetime.datetime.utcfromtimestamp(timestamp)
    return date.strftime(format)

@filter_function
def timestamp_to_naturaldate(timestamp):
    return timestamp_to_string(timestamp, '%B %d, %Y')

####################################################################################################

@global_function
def make_attributes(*booleans, **keyvalues):
    keyvalues = {
        key.replace('_', '-'): value
        for (key, value) in keyvalues.items()
        if value is not None
    }
    attributes = [f'{key}="{jinja2.filters.escape(value)}"' for (key, value) in keyvalues.items()]
    attributes.extend(booleans)
    attributes = ' '.join(attributes)
    return attributes
