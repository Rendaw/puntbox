import os
import argparse
import hashlib
import base64
import urllib
import json
import time
import datetime
import traceback
import signal
import subprocess
import logging
import logging.handlers

import luxem
import requests
import bencode
import watchdog
import watchdog.events
import watchdog.observers

die = False
def signal_handler(signal, frame):
    global die
    die = True
signal.signal(signal.SIGINT, signal_handler)

config_path = None
internal_path = None
torrent_path = None
box_path = None
magnets_path = None

class TransmissionSession(object):
    def __init__(self, url):
        self.url = url
        session_start = requests.post(
            self.url, 
            data=json.dumps({
                    'method': 'session-get',
                    'arguments': {
                    },
                },
                indent=4
            ),
            timeout=10,
        )
        self.headers = {
            'X-Transmission-Session-Id': session_start.headers['X-Transmission-Session-Id']
        }

    def post(self, data):
        return requests.post(
            self.url,
            data=data,
            headers=self.headers,
            timeout=10,
        )

def run(args):
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out, err = proc.communicate()
    logging.debug(out)
    logging.error(err)
    if proc.returncode != 0:
        logging.error('Failed to create torrent!')
        return False
    return True

class Manager(object):
    comment = []
    tracker = None

    def __init__(self):
        def parse_root(root):
            root.element('comment', 
                lambda array: array.element(
                    lambda element: self.comment.append(element)
                )
            )
            root.element('tracker', lambda tracker: setattr(self, 'tracker', tracker))
            def parse_transmission(obj):
                obj.element('url', lambda url: setattr(self, 'transmission_url', url))
            root.element('transmission', parse_transmission)
        with open(config_path, 'r') as config_file:
            luxem.Reader().element(parse_root).feed(config_file)
        if not self.tracker:
            raise TypeError('Tracker config missing!')

    def get_torrent_path(self, path):
        return os.path.join(torrent_path, path + '.torrent')

    def create(self, path):
        # create torrent
        comment = []
        for element in self.comment:
            if isinstance(element, luxem.Typed):
                if element.name == 'filename':
                    comment.append(path)
                elif element.name == 'timestamp':
                    comment.append(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                elif element.name == 'br':
                    comment.append('\n')
                else:
                    logging.error('Unknown comment element {}'.format(element))
            else:
                comment.append(element)
        comment = ''.join(comment)
        logging.debug('Comment is: "{}"'.format(comment))
        torrent = self.get_torrent_path(path)
        if not run([
            'transmission-create',
            '-o', torrent,
            '-c', comment,
            '-t', self.tracker,
            os.path.join(box_path, path),
        ]):
            return

        # register torrent
        session = TransmissionSession(self.transmission_url)
        session.post(
            data=json.dumps({
                    'method': 'torrent-add',
                    'arguments': {
                        'filename': torrent,
                        'download-dir': torrent_path,
                    },
                },
                indent=4
            ),
        )

        # create magnet link
        # Thanks jterrace @ http://stackoverflow.com/questions/12479570/given-a-torrent-file-how-do-i-generate-a-magnet-link-in-python/12480263#12480263
        torrent = open(torrent, 'r').read()
        metadata = bencode.bdecode(torrent)
        hashcontents = bencode.bencode(metadata['info'])
        digest = hashlib.sha1(hashcontents).digest()
        b32hash = base64.b32encode(digest)
        params = {
            'xt': 'urn:btih:{}'.format(b32hash), 
            'dn': metadata['info']['name'],
            'tr': metadata['announce'],
            'xl': metadata['info']['length']
        }
        magnet = 'magnet:?{}'.format(urllib.urlencode(params))

        magnets = {}
        try:
            with open(magnets_path, 'r') as magnets_file:
                # Load existing magnets
                magnets = luxem.read_struct(magnets_file)
                magnets = next(iter(magnets), {})
        except:
            pass

        # Add magnet
        magnets[path] = magnet

        # Write magnets
        with open(magnets_path, 'w') as magnets_file:
            luxem.Writer(magnets_file, pretty=True).value(magnets)

    def delete(self, path):
        # deregister torrent
        torrent = self.get_torrent_path(path)
        session = TransmissionSession(self.transmission_url)
        torrent_files = session.post(
            data=json.dumps({
                    'method': 'torrent-get',
                    'arguments': {
                        'fields': ['torrentFile', 'id'],
                    },
                },
                indent=4
            ),
        )
        for compare in torrent_files.json()['arguments']['torrents']:
            if compare['torrentFile'] == torrent:
                session.post(
                    data=json.dumps({
                            'method': 'torrent-remove',
                            'arguments': {
                                'ids': [compare['id']],
                                'delete-local-data': False,
                            },
                        },
                        indent=4
                    ),
                )

        # delete torrent
        try:
            os.remove(torrent)
        except:
            pass
    
class MonitorHandler(watchdog.events.FileSystemEventHandler):
    manager = None

    def on_any_event(self, event):
        actions = []
        if isinstance(event, (watchdog.events.FileMovedEvent, watchdog.events.DirMovedEvent)):
            actions.extend([
                ('delete', event.src_path),
                ('create', event.dest_path),
            ])
        elif isinstance(event, (watchdog.events.FileModifiedEvent, watchdog.events.DirModifiedEvent)):
            actions.extend([
                ('modify', event.src_path),
            ])
        elif isinstance(event, (watchdog.events.FileCreatedEvent, watchdog.events.DirCreatedEvent)):
            actions.extend([
                ('create', event.src_path),
            ])
        elif isinstance(event, (watchdog.events.FileDeletedEvent, watchdog.events.DirDeletedEvent)):
            actions.extend([
                ('delete', event.src_path),
            ])

        for action, path in actions:
            path = path[len(box_path):]
            if not path: 
                continue
            if path[0] == '/':
                path = path[1:]
            if any([
                seg.startswith('.') and not (
                    seg == '.' or
                    seg == '..'
                ) for seg in os.path.split(path)
            ]):
                continue
            if path == 'magnets.luxem':
                continue
            try:
                if path == 'config.luxem':
                    if action == 'create':
                        self.manager = Manager()
                    elif action == 'delete':
                        self.manager = None
                    elif action == 'modify':
                        self.manager = Manager()
                elif self.manager:
                    if action == 'create':
                        self.manager.create(path)
                    elif action == 'delete':
                        self.manager.delete(path)
                    elif action == 'modify':
                        self.manager.delete(path)
                        self.manager.create(path)
            except:
                global die
                die = True
                logging.error('Error handling \'{}\' on {}: {}'.format(
                    action,
                    path,
                    traceback.format_exc()
                ))

def main():
    parser = argparse.ArgumentParser(
        description='Create and seed torrents when files are added to a directory.',
    )
    parser.add_argument(
        'box', 
        help='Path to watched directory. Will be created if it doesn\'t exist.'
    )
    args = parser.parse_args()
    
    global box_path
    box_path = args.box
    
    try:
        os.makedirs(box_path)
    except:
        pass

    global magnets_path
    magnets_path = os.path.join(box_path, 'magnets.luxem')
    global config_path
    config_path = os.path.join(box_path, 'config.luxem')
    global internal_path
    internal_path = os.path.join(box_path, '.puntbox')
    global torrent_path
    torrent_path = os.path.join(internal_path, 'torrents')
    if not os.path.exists(config_path):
        with open(config_path, 'w') as config_file:
            (
                luxem.Writer(config_file, pretty=True).object_begin()
                    .key('tracker').value('udp://open.demonii.com:1337/announce')
                    .key('transmission').object_begin()
                        .key('url').value('http://127.0.0.1:9091/transmission/rpc')
                    .object_end()
                    .key('comment').array_begin()
                        .value('Torrent published by puntbox!')
                        .type('br').value('')
                        .value('Created: ').type('timestamp').value('')
                        .type('br').value('')
                        .value('Contents: ').type('filename').value('')
                    .array_end()
                .object_end()
            )

            try:
                os.makedirs(internal_path)
            except:
                pass

            with open(os.path.join(internal_path, 'ignore_this_directory_please'), 'w') as note:
                pass
            
            try:
                os.makedirs(torrent_path)
            except:
                pass

            print('Puntbox initialized!')
            print('Assuming the settings are correct, you can now publish files by putting them in {}.'.format(box_path))
            print('Magnets links will appear in {}.'.format(magnets_path))
    
    log = logging.getLogger()
    log.setLevel(logging.DEBUG)
    log.addHandler(logging.handlers.RotatingFileHandler(
        os.path.join(internal_path, 'log.txt'), 
        maxBytes=256 * 1024, 
        backupCount=4
    ))
 
    Manager.log = log
    handler = MonitorHandler()
    handler.log = log
    handler.manager = Manager()
	
    observer = watchdog.observers.Observer()
    observer.schedule(handler, box_path, recursive=False)
    observer.start()
    try:
        while not die:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    observer.stop()
    observer.join()

if __name__ == '__main__':
    main()
