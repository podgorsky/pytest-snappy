import sys
from base64 import b64decode
from contextlib import contextmanager
from errno import EEXIST
from json import dumps
from os import path, makedirs, getcwd
from typing import overload

import numpy as np
from cv2 import cv2
from pytest import skip
from selenium.common.exceptions import WebDriverException
from skimage.metrics import structural_similarity as ssim

if sys.version_info >= (3, 8):
    from functools import singledispatchmethod


class SnapSizeError(AssertionError):
    """ Sizes of provided images are not equal. """


class SnapDifferenceError(AssertionError):
    """ Contents of provided images are not equal. """


class SnapTypeError(TypeError):
    """ Invalid data type given. """


class SnapshotComparator(object):
    """
    Class that calculates the difference between two provided images and creates difference image.
    """

    def __init__(self, output_snap, reference_snap):
        self.output_snap = self._read_snap(output_snap)
        self.reference_snap = self._read_snap(reference_snap)

        self._ssim_equality = None
        self._difference_image = None
        self._get_equality_and_diff_image()

    @property
    def difference(self):
        return round(((1 - self._ssim_equality) * 100), 4)

    @property
    def difference_image(self):
        return cv2.imencode('.png', self._draw_contours())[1].tobytes()

    def _get_equality_and_diff_image(self):
        self._ssim_equality, self._difference_image = ssim(*self._get_grayscale(), full=True, gaussian_weights=True)

    def _get_grayscale(self):
        return cv2.cvtColor(self.reference_snap, cv2.COLOR_BGR2GRAY), cv2.cvtColor(self.output_snap, cv2.COLOR_BGR2GRAY)

    def _draw_contours(self):
        contours = cv2.findContours(
            cv2.threshold(
                (self._difference_image * 255).astype('uint8'), 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU
            )[1],
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )
        contours = contours[0] if len(contours) == 2 else contours[1]

        alpha = 0.6
        color = (0, 255, 0, 125)
        return cv2.addWeighted(
            cv2.drawContours(self.output_snap.copy(), contours, -1, color, -1), alpha, self.output_snap, 1 - alpha, 0
        )

    if sys.version_info >= (3, 8):
        @singledispatchmethod
        def _read_snap(self, snap):
            raise SnapTypeError(f'{type(snap)} is an unsupported type, expected - {bytes}, {str}')

        @_read_snap.register
        def _(self, snap: str):
            return cv2.imread(snap)

        @_read_snap.register
        def _(self, snap: bytes):
            return cv2.imdecode(np.asarray(bytearray(snap), dtype=np.uint8), cv2.IMREAD_COLOR)

    else:
        @overload
        def _read_snap(self, snap: str) -> np.ndarray: ...
        @overload
        def _read_snap(self, snap: bytes) -> np.ndarray: ...

        def _read_snap(self, snap):
            if isinstance(snap, str):
                return cv2.imread(snap)
            elif isinstance(snap, bytes):
                return cv2.imdecode(np.asarray(bytearray(snap), dtype=np.uint8), cv2.IMREAD_COLOR)
            else:
                raise SnapTypeError(f'{type(snap)} is an unsupported type, expected - {bytes}, {str}')


class Asserter(SnapshotComparator):
    """
    Class asserting that the difference between two provided images is under the difference_limit.
    """
    def __init__(self, output_snap, reference_snap, difference_limit=0):
        self.difference_limit = difference_limit

        super().__init__(output_snap, reference_snap)

    def assert_snap(self):
        if self.output_snap.shape != self.reference_snap.shape:
            raise SnapSizeError(
                f'Screenshot sizes do not match.\n'
                f'New screenshot size - {self.output_snap.shape[0]} на {self.output_snap.shape[1]},'
                f'reference size - {self.reference_snap.shape[0]} на {self.reference_snap.shape[1]}.'
            )
        if self.difference > self.difference_limit:
            raise SnapDifferenceError(
                f'The difference between new screenshot and reference ({self.difference}) '
                f'exceeds acceptable limit ({self.difference_limit})')


class Snappy(object):
    """
    Main pytest-snappy class that implements comparing methods used in test functions.
    """
    def __init__(self, driver, refresh_reference):
        """
        Snappy object initialization method.

        :param driver: Instance of Selenium WebDriver
        :param refresh_reference: Boolean value specified on the command line
        by '--refresh_references' parameter (False by default)
        """
        self.driver = driver
        self.refresh_reference = refresh_reference

        self.fullpage = True
        self.mask_locators = None
        self.locator = None

        self.filename = None

        self.output_snap = None
        self.difference_image = None

        self.reference_directory = path.realpath(path.join(getcwd(), 'snap_references'))
        try:
            makedirs(self.reference_directory)
        except OSError as error:
            if error.errno == EEXIST:
                pass
            else:
                raise error

        self.driver.maximize_window()

    def assert_snapshots(self, difference_limit=0) -> None:
        """
        Assert-variant of compare_snapshots method for situations when you dont need context manager functionality.
        For example, when all operations before the screenshot is taken are guaranteed to complete.

        :param difference_limit: Difference threshold, upon exceeding which an exception will be raised (0 by default).
        """
        with self.compare_snapshots(difference_limit):
            pass

    @contextmanager
    def compare_snapshots(self, difference_limit=0) -> None:
        """
        Context manager for performing screenshot comparing (using the Asserter class),
        reference saving and errors raising in cases when screenshots contents or sizes are different.

        :param difference_limit: Difference threshold, upon exceeding which an exception will be raised (0 by default).
        """
        yield

        reference_file = path.join(self.reference_directory, f'{self.filename}.png')

        if self.fullpage:
            if self.mask_locators:
                self._mask_elements()
            self.output_snap = self._get_fullpage_screenshot_as_bytes()
        elif self.locator:
            self.output_snap = self._get_element_screenshot_as_bytes()
        else:
            raise

        if not path.isfile(reference_file) or self.refresh_reference:
            with open(reference_file, 'wb') as file:
                file.write(self.output_snap)
            skip(
                'Reference snapshot is missing or out of date. '
                'The current screenshot is saved as a reference.'
            )
        else:
            asserter = Asserter(self.output_snap, reference_file, difference_limit)
            try:
                asserter.assert_snap()
            except SnapDifferenceError as error:
                self.difference_image = asserter.difference_image
                raise error
            except SnapSizeError as error:
                self.difference_image = self.output_snap
                raise error

    def _mask_elements(self) -> None:
        """
        Masks (makes transparent) elements found by locators in self.mask_locators
        (in order to hide dynamic elements on page).
        """
        for locator in self.mask_locators:
            for element in self.driver.find_elements(*locator):
                try:
                    self.driver.execute_script('arguments[0].setAttribute("style", "opacity:0;");', element)
                except WebDriverException as error:
                    print('Error : ', str(error))
                    raise error

    def _get_fullpage_screenshot_as_bytes(self) -> bytes:
        """
        Makes screenshot of full page and returns it as bytes (may not work in non-chromium browsers).

        :return: Byte type full page screenshot
        """
        def send(cmd, params):
            resource = f'/session/{self.driver.session_id}/chromium/send_command_and_get_result'
            url = self.driver.command_executor._url + resource
            body = dumps({'cmd': cmd, 'params': params})
            response = self.driver.command_executor._request('POST', url, body)
            return response.get('value')

        def evaluate(script):
            response = send('Runtime.evaluate', {'returnByValue': True, 'expression': script})
            return response['result']['value']

        metrics = evaluate("""
            ({
                width: Math.max(window.innerWidth, document.body.scrollWidth, document.documentElement.scrollWidth)|0,
                height: Math.max(innerHeight, document.body.scrollHeight, document.documentElement.scrollHeight)|0,
                deviceScaleFactor: window.devicePixelRatio || 1,
                mobile: typeof window.orientation !== "undefined"
            })
        """)
        send('Emulation.setDeviceMetricsOverride', metrics)
        screenshot = send('Page.captureScreenshot', {'format': 'png', 'fromSurface': True})
        send('Emulation.clearDeviceMetricsOverride', {})

        return b64decode(screenshot['data'])

    def _get_element_screenshot_as_bytes(self) -> bytes:
        """
        Makes screenshot of element found by self.locator.

        :return: Byte type element screenshot
        """
        return self.driver.find_element(*self.locator).screenshot_as_png
