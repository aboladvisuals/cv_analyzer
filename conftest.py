# conftest.py (project root)
#
# This file can stay empty. Its only job is to exist here, at the project
# root, so that pytest treats this folder as a "rootdir" and adds it to
# sys.path before collecting tests. Without this, files under tests/ that
# do `import config` or `import cv_parser` fail with:
#   ModuleNotFoundError: No module named 'config'
# because pytest wouldn't otherwise know the project root should be
# importable.
