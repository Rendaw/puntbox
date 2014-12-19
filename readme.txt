puntbox creates and begins seeding torrents when files are added to a directory.  

- puntbox uses transmission bittorrent to handle torrent creation and seeding, so make sure that is running before putting files in your box.

- Configuration is specified in config.luxem in your box directory.  puntbox watches the config.luxem and automatically reconfigures when it changes.

- magnets.luxem contains an updated list of magnet links for all created torrents.  Don't mess with this file!

- If things are not working, check .puntbox/log.txt within your box directory.

----
usage: puntbox.py [-h] box

Create and seed torrents when files are added to a directory.

positional arguments:
  box         Path to watched directory. Will be created if it doesn't exist.

optional arguments:
  -h, --help  show this help message and exit
