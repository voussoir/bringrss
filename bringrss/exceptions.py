from voussoirkit import stringtools

class ErrorTypeAdder(type):
    '''
    During definition, the Exception class will automatically receive a class
    attribute called `error_type` which is just the class's name as a string
    in the loudsnake casing style. NoSuchFeed -> NO_SUCH_FEED.

    This is used for serialization of the exception object and should
    basically act as a status code when displaying the error to the user.

    Thanks Unutbu
    http://stackoverflow.com/a/18126678
    '''
    def __init__(cls, name, bases, clsdict):
        type.__init__(cls, name, bases, clsdict)
        cls.error_type = stringtools.pascal_to_loudsnakes(name)

class BringException(Exception, metaclass=ErrorTypeAdder):
    '''
    Base type for all of the BringRSS exceptions.
    Subtypes should have a class attribute `error_message`. The error message
    may contain {format} strings which will be formatted using the
    Exception's constructor arguments.
    '''
    error_message = ''

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.given_args = args
        self.given_kwargs = kwargs
        self.error_message = self.error_message.format(*args, **kwargs)
        self.args = (self.error_message, args, kwargs)

    def __str__(self):
        return f'{self.error_type}: {self.error_message}'

    def jsonify(self):
        j = {
            'type': 'error',
            'error_type': self.error_type,
            'error_message': self.error_message,
        }
        return j

# NO SUCH ##########################################################################################

class NoSuch(BringException):
    pass

class NoSuchFeed(NoSuch):
    error_message = 'Feed "{}" does not exist.'

class NoSuchFilter(NoSuch):
    error_message = 'Filter "{}" does not exist.'

class NoSuchNews(NoSuch):
    error_message = 'News "{}" does not exist.'

# XML PARSING ERRORS ###############################################################################

class BadXML(BringException):
    error_message = '{}'

class NeitherAtomNorRSS(BadXML):
    error_message = '{}'

class NoGUID(BadXML):
    error_message = '{}'

# FEED ERRORS ######################################################################################

class HTTPError(BringException):
    error_message = '{}'

class InvalidHTTPHeaders(BringException):
    error_message = '{}'

# FILTER ERRORS ####################################################################################

class FeedStillInUse(BringException):
    error_message = 'Cannot delete {feed} because it is used by {filters}.'

class FilterStillInUse(BringException):
    error_message = 'Cannot delete {filter} because it is used by feeds {feeds}.'

class InvalidFilter(BringException):
    error_message = '{}'

class InvalidFilterAction(InvalidFilter):
    error_message = '{}'

class InvalidFilterCondition(InvalidFilter):
    error_message = '{}'

# GENERAL ERRORS ###################################################################################

class BadDataDirectory(BringException):
    '''
    Raised by BringDB __init__ if the requested data_directory is invalid.
    '''
    error_message = 'Bad data directory "{}"'

OUTOFDATE = '''
Database is out of date. {existing} should be {new}.
Please run utilities\\database_upgrader.py "{filepath.absolute_path}"
'''.strip()
class DatabaseOutOfDate(BringException):
    '''
    Raised by BringDB __init__ if the user's database is behind.
    '''
    error_message = OUTOFDATE

class NoClosestBringDB(BringException):
    '''
    For calls to BringDB.closest_photodb where none exists between cwd and
    drive root.
    '''
    error_message = 'There is no BringDB in "{}" or its parents.'

class NotExclusive(BringException):
    '''
    For when two or more mutually exclusive actions have been requested.
    '''
    error_message = 'One and only one of {} must be passed.'

class OrderByBadColumn(BringException):
    '''
    For when the user tries to orderby a column that does not exist or is
    not allowed.
    '''
    error_message = '"{column}" is not a sortable column.'

class OrderByBadDirection(BringException):
    '''
    For when the user tries to orderby a direction that is not asc or desc.
    '''
    error_message = 'You can\'t order "{column}" by "{direction}". Should be asc or desc.'

class OrderByInvalid(BringException):
    '''
    For when the orderby request cannot be parsed into column and direction.
    For example, it contains too many hyphens like a-b-c.

    If the column and direction can be parsed but are invalid, use
    OrderByBadColumn or OrderByBadDirection
    '''
    error_message = 'Invalid orderby request "{request}".'
