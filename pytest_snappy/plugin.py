from os import path

from pytest import fixture, mark

from snap import Snap


def pytest_addoption(parser):
    parser.addoption(
        '--refresh_references',
        action='store_true',
        help=''
    )
    parser.addoption(
        '--save_successful',
        action='store_true',
        help=''
    )


@fixture
def snap(selenium, request):
    snap = Snap(selenium, request.config.getoption('refresh_references'))
    snap.filename = request.node.name

    yield snap


@mark.hookwrapper
@mark.trylast
def pytest_runtest_makereport(item, call):
    outcome = yield
    result = outcome.get_result()

    if 'snap' in item.fixturenames and call.when == 'call':
        snap = item.funcargs['snap']

        xfail = hasattr(result, 'wasxfail')
        fail = result.failed
        if fail or xfail or item.config.getoption('save_successful'):
            with open(path.join(item.funcargs['tmpdir'].dirname, f'{snap.filename}.png'), 'wb') as file:
                file.write(snap.difference_image or snap.output_snap)

            if item.config.pluginmanager.hasplugin('allure'):
                try:
                    import allure
                except ImportError:
                    pass
                else:
                    allure.attach(
                        snap.difference_image or snap.output_snap,
                        name='current_snapshot',
                        attachment_type=allure.attachment_type.PNG
                    )
