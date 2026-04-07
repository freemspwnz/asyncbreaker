#!/usr/bin/env python
# -*- coding:utf-8 -*-

from pathlib import Path
from setuptools import setup, find_packages

version_ns = {}
exec(Path("asyncbreaker/version.py").read_text(encoding="utf-8"), version_ns)


with open("readme.rst", "r") as fh:
    long_description = fh.read()

test_dependencies = ['fakeredis', 'pytest>4', 'pytest-asyncio',
                     'mypy', 'pylint', 'safety', 'bandit', 'codecov', 'pytest-cov']
redis_dependencies = ['redis']
documentation_dependencies = [
    'sphinx', 'sphinx_rtd_theme', 'sphinx-autobuild', 'sphinx-autodoc-typehints']

setup(
    name='asyncbreaker',
    version=version_ns["__version__"],
    url='https://github.com/freemspwnz/asyncbreaker',
    license='BSD',
    author='Sergey Turbinov',
    description='Asyncio Circuit Breaker pattern with optional Redis storage.',
    long_description=long_description,
    long_description_content_type='text/x-rst',
    packages=find_packages(),
    python_requires='>=3.10',
    project_urls={
        'Source': 'https://github.com/freemspwnz/asyncbreaker',
        'Telegram': 'https://t.me/freems',
    },
    install_requires=[],
    tests_require=test_dependencies,
    extras_require={
        'test': test_dependencies,
        'docs': documentation_dependencies,
        'redis': redis_dependencies,
    },
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Framework :: AsyncIO',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
