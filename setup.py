from setuptools import setup, find_packages
from os import path
from atavism import __version__
import io


here = path.abspath(path.dirname(__file__))

# Get the long description from the relevant file
with io.open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()


setup(
    name='atavism',
    version=__version__,
    description='Module to play video to an AppleTV',
    long_description=long_description,
    url='https://github.com/zathras777/atavism',
    author='david reid',
    author_email='zathrasorama@gmail.com',
    license='Unlicense',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Multimedia :: Video :: Display',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.4',
    ],
    keywords='appletv video ffmpeg streaming',
    packages=find_packages(exclude=['tests']),
    test_suite='tests',
    entry_points={
        'console_scripts': ['atavism=atavism.command_line:main']
    },
    download_url = 'https://github.com/zathras777/atavism/tarball/0.1',
)
