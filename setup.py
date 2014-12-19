from setuptools import setup

setup(
    name = 'puntbox',
    version = '0.0.1',
    author = 'Rendaw',
    author_email = 'spoo@zarbosoft.com',
    packages = ['puntbox'],
    url = 'https://github.com/Rendaw/puntbox',
    download_url = 'https://github.com/Rendaw/puntbox/tarball/v0.0.1',
    license = 'BSD',
    description = 'Give your torrent publishing a kick start!',
    long_description = open('readme.txt', 'r').read(),
    classifiers = [
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Topic :: Communications :: File Sharing',
        'License :: OSI Approved :: BSD License',
    ],
    install_requires = [
        'luxem',
        'requests',
        'bencode',
        'watchdog',
    ],
    entry_points = {
        'console_scripts': [
            'puntbox = puntbox.puntbox:main',
        ],
    }
)
