Contributing to asyncbreaker
==========================

Contributions are welcome: bug reports, discussion, fixes, and feature proposals.

Getting started
---------------

There are no mandatory runtime dependencies (optional ``redis`` for Redis storage).

.. code:: bash

    python -m venv .venv
    source .venv/bin/activate   # or .venv\\Scripts\\activate on Windows
    pip install -e '.[test]'
    pytest test

To build the documentation:

.. code:: bash

    pip install -e '.[docs]'
    sphinx-build docs/source docs/build

Release (maintainers)
---------------------

Releases are typically published with ``twine``:

.. code:: bash

    pip install twine build
    python -m build
    twine upload dist/*

License
-------

By contributing, you agree that your contributions will be licensed under the same terms as
the project: **BSD 3-Clause** (see ``license.md``).
