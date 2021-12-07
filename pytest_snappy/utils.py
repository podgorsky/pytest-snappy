class SnapLocatorsMixin:
    """ Миксин для класса локаторов, позволяющий итерировать через значения локаторов. """
    def __iter__(self):
        for attribute in filter(lambda attribute_name: not attribute_name.startswith('__'), dir(self)):
            yield getattr(self, attribute)
