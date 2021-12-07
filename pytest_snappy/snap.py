from base64 import b64decode
from contextlib import contextmanager
from errno import EEXIST
from functools import singledispatchmethod
from json import dumps
from os import path, makedirs, getcwd

import numpy as np
from cv2 import cv2
from pytest import skip
from selenium.common.exceptions import WebDriverException
from skimage.metrics import structural_similarity as ssim


class SnapSizeError(AssertionError):
    """ Размеры изображений отличаются."""


class SnapDifferenceError(AssertionError):
    """ Изображения отличаются. """


class SnapTypeError(TypeError):
    """ Недопустимый тип данных. """


class SnapshotComparator(object):
    """
    Класс, вычисляющий разницу между двумя изображениями.
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

    @singledispatchmethod
    def _read_snap(self, snap):
        raise SnapTypeError(f'{type(snap)} является неподдерживаемым типом, ожидалось - {bytes}, {str}')

    @_read_snap.register
    def _(self, snap: str):
        return cv2.imread(snap)

    @_read_snap.register
    def _(self, snap: bytes):
        return cv2.imdecode(np.asarray(bytearray(snap), dtype=np.uint8), cv2.IMREAD_COLOR)


class Asserter(SnapshotComparator):
    """
    Класс, осуществляющий сравнение двух изображений.
    """
    def __init__(self, output_snap, reference_snap, difference_limit=0):
        self.difference_limit = difference_limit

        super().__init__(output_snap, reference_snap)

    def assert_snap(self):
        if self.output_snap.shape != self.reference_snap.shape:
            raise SnapSizeError(
                f'Размер скриншотов не совпадает.\n'
                f'Размер нового скриншота {self.output_snap.shape[0]} на {self.output_snap.shape[1]},'
                f'размер образца - {self.reference_snap.shape[0]} на {self.reference_snap.shape[1]}.'
            )
        if self.difference > self.difference_limit:
            raise SnapDifferenceError(
                f'Разница между новым скриншотом и образцом ({self.difference}) '
                f'превышает допустимое значение ({self.difference_limit})')


class Snap(object):
    def __init__(self, driver, refresh_reference):
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

    def assert_snapshots(self, threshold=0):
        """assert-style variant of compareScreenshot context manager
        compareScreenshot() can be considerably more efficient for recording baselines by avoiding the need
        to load pages before checking whether we're actually going to save them. This function allows you
        to continue using normal unittest-style assertions if you don't need the efficiency benefits
        """

        with self.compare_snapshots(threshold):
            pass

    @contextmanager
    def compare_snapshots(self, threshold=0):
        """
        Assert that a screenshot of an element is the same as a screenshot on disk,
        within a given threshold.
        :param threshold:
            The threshold for triggering a test failure.
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
                'Образец изображения отсутствует или неактуален. '
                'Текущее изображение сохранено в качестве образца.'
            )
        else:
            asserter = Asserter(self.output_snap, reference_file, threshold)
            try:
                asserter.assert_snap()
            except SnapDifferenceError as error:
                self.difference_image = asserter.difference_image
                raise error
            except SnapSizeError as error:
                self.difference_image = self.output_snap
                raise error

    def _mask_elements(self):
        for locator in self.mask_locators:
            for element in self.driver.find_elements(*locator):
                try:
                    self.driver.execute_script('arguments[0].setAttribute("style", "opacity:0;");', element)
                except WebDriverException as error:
                    print('Error : ', str(error))
                    raise error

    def _get_fullpage_screenshot_as_bytes(self):
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

    def _get_element_screenshot_as_bytes(self):
        return self.driver.find_element(*self.locator).screenshot_as_png
