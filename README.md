pytest-snappy
---
A plugin for snapshot UI testing with `pytest` and `Selenium`.

Features
---
- Snappy tests run like regular pytest tests.
- Screenshots web page and saves result to `snap_references` directory or asserts that 
difference between already saved screenshot and current is less than `snap.difference_limit`
- A screenshot of a single element can be taken by passing element's locator to `snap.locator` variable
- Fullpage screenshot is taken by default, this behavior can be changed by passing  `snap.locator` variable or `snap.fullpage=False`
- Hides specified locators passed to `snap.mask_locators` variable 
- Screenshots must be the same size, otherwise `SnapSizeError` is raised

Installation
---
Python 3.6-3.10 supported.
Install with:
```
python -m pip install git+https://github.com/podgorsky/pytest-snappy.git@main
```

In conftest.py:
```python
pytest_plugins = ["snappy"]
```

Usage
---
Simple usage example: 

```python
from selenium.webdriver.common.by import By
from pytest_snappy.utils import SnapLocatorsMixin


# Mask locators for hiding elements, locators with _ will be ignored.
class MaskLocatorsClass(SnapLocatorsMixin):
    EXAMPLE_ELEMENT = (
        By.XPATH,
        '//div[@class="example-element"]',
    )
    _SUBCATEGORIES_COUNTER = (
        By.CSS_SELECTOR,
        '.example-element',
    )


# Snap fixture connected in conftest.py contains webdriver instance 
# that can be used to open web pages.
def test_example(snap):
    snap.mask_locators = MaskLocatorsClass()
    snap.driver.get(url='https://www.example.com/')
    snap.assert_snapshots(difference_limit=5)
    # Exceeding the image difference limit will result in an SnapDifferenceError.
```