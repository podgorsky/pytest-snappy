from os import path

from pytest import fixture, mark

from .snappy import Snappy
from .utils import validate_filename


ALLURE_ERROR_MESSAGE = 'Screenshot not found. Please make sure the locator finds the element on the page.'

def pytest_addoption(parser):
    parser.addoption(
        '--refresh_references',
        action='store_true',
        help='Overwrite existing snapshot references with screenshots created in the current test run'
    )
    parser.addoption(
        '--save_successful',
        action='store_true',
        help='Save all output screenshots in tempdir'
    )


@fixture
def snap(selenium, request):
    """
    Main pytest-snappy fixture that yields initialized Snap object in test function.
    """
    snappy = Snappy(selenium, request.config.getoption('refresh_references'))
    snappy.filename = validate_filename(request.node.name)

    yield snappy


@mark.hookwrapper
@mark.trylast
def pytest_runtest_makereport(item, call):
    outcome = yield
    result = outcome.get_result()

    if 'snap' in item.fixturenames and call.when == 'call':
        snappy = item.funcargs['snap']

        xfail = hasattr(result, 'wasxfail')
        fail = result.failed
        if fail or xfail or item.config.getoption('save_successful'):
            if snappy.difference_image or snappy.output_snap:
                with open(path.join(item.funcargs['tmpdir'].dirname, f'{snappy.filename}.png'), 'wb') as file:
                    file.write(snappy.difference_image or snappy.output_snap)

            if item.config.pluginmanager.hasplugin('allure_pytest'):
                try:
                    import allure
                except ImportError:
                    pass
                else:
                    allure.attach(
                        snappy.difference_image or snappy.output_snap or ALLURE_ERROR_MESSAGE,
                        name='current_snapshot',
                        attachment_type=allure.attachment_type.PNG
                        if snappy.difference_image or snappy.output_snap
                        else allure.attachment_type.TEXT
                    )
