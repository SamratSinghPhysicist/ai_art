from setuptools import setup, find_packages

setup(
    name="stability_api_generator",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "requests",
        "selenium",
        "webdriver-manager",
        "pyperclip",
    ],
    py_modules=["temp_mail"]
) 