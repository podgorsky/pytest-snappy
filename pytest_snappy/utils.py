from re import sub


class SnapLocatorsMixin:
    """ A mixin for class containing Selenium locators that allows you to iterate through locators values. """
    def __iter__(self):
        for attribute in filter(lambda attribute_name: not attribute_name.startswith('__'), dir(self)):
            yield getattr(self, attribute)


def validate_filename(name):
    return sub(r'(?u)[^\w]+', '_', str(name).strip()).strip('_')
