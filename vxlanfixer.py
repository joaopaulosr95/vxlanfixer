#!/usr/bin/python
# -*- coding: utf-8 -*-

""" This is a simple tool to fix FDB missing entries in an Docker overlay
environment using Consul. Sometimes with improper start/stop of containers,
some garbage may be placed in host vxlan routing tables, and suddenly some
your containers begin to miscommunicate with each other.
"""

import consul
import docker
import json
import os
import subprocess
import yaml
from argparse import ArgumentParser
from nsenter import Namespace

class VXLANFixer:

    def __init__(self, **config):
        self.config = config
        docker_daemon_url = 'tcp://' + self.config['docker']['host'] + ':' \
            + str(self.config['docker']['port'])
        self.docker_client = docker.DockerClient(base_url=docker_daemon_url)
        self.consul_client = consul.Consul(host=self.config['consul']['host'],
                                           port=config['consul']['port'])
        self.consul_endpoints = list()
        self.fdb_endpoints = list()

        try:
            network = self.docker_client.networks.list(
                names=[self.config['netns']])[0]
            self.vxlan = {
                'id': str(network.id),
                'name': str(network.name),
                'filepath': None,
                'device': self.config['device'],
                }
        except IndexError:
            print('Network namespace %s not found' % self.config['netns'])
            exit(1)

        netnspath = '/var/run/docker/netns'
        try:
            netns_list = [f for f in os.listdir(netnspath)
                          if os.path.isfile(os.path.join(netnspath, f))]
            for n in netns_list:
                """ there is a convention that every overlay namespace have
                    the <character>-<ID> format, while a local network
                    namespace have the <ID> format, so try to split this name
                    and get the second field for substring match
                """
                try:
                    if n.split('-')[1] in self.vxlan['id']:
                        self.vxlan['filepath'] = os.path.join(netnspath, n)
                        return
                except IndexError:
                    continue
            raise OSError(2, 'No netns file corresponding to %s in %s'
                          % (self.vxlan['name'], netnspath))
        except OSError, err:
            print err
            exit(1)

    def get_consul_endpoints(self):
        (_, data) = self.consul_client.kv.get('docker/network/v1.0/endpoint/',
                                              recurse=True)
        epdata = [e['Value'] for e in data if e['Value'] is not None]

        for ep in epdata:
            j = json.loads(ep.encode('utf-8'))
            self.consul_endpoints.append(
                tuple([j['ep_iface']['mac'].encode('utf-8'),
                       j['locator'].encode('utf-8')]))

    def dump_consul_endpoints(self):
        if len(self.consul_endpoints) == 0:
            self.get_consul_endpoints()
        print '{0:17s} {1:10s}'.format('mac', 'locator')
        for tup in self.consul_endpoints:
            print '{0:17s} {1:10s}'.format(tup[0], tup[1])

    def get_fdb_endpoints(self):
        with Namespace(self.vxlan['filepath'], 'net'):
            o = subprocess.check_output(['bridge', 'fdb', 'show', 'br0'])

            fdb_ep = filter(
                lambda x: 'dst' in x and self.vxlan['device'] in x,
                o.split('\n'))

            for ep in fdb_ep:
                (mac, locator) = (lambda x: [x[0], x[4]])(ep.split(' '))
                self.fdb_endpoints.append(tuple([mac, locator]))

    def dump_fdb_endpoints(self):
        if len(self.fdb_endpoints) == 0:
            self.get_fdb_endpoints()
        for tup in self.fdb_endpoints:
            print '{0:17s} {1:10s}'.format(tup[0], tup[1])

    def find_messy_entries(self):
        if len(self.consul_endpoints) == 0:
            self.get_consul_endpoints()
        if len(self.fdb_endpoints) == 0:
            self.get_fdb_endpoints()

        # check different entries in consul_endpoints and fdb_endpoints and
        # replace them
        replace_list = [tuple([c_tup[0], f_tup[1], c_tup[1]])
                        for c_tup in self.consul_endpoints for f_tup in
                        self.fdb_endpoints if f_tup[0] == c_tup[0]
                        and f_tup[1] != c_tup[1] and f_tup[1] != '127.0.0.1']
        if len(replace_list) > 0:
            print '--- To replace ---'
            for r in replace_list:
                print '{0:} from {1:} to {2:}'.format(r[0], r[1], r[2])
        else:
            print 'Nothing to replace'

        # check missing entries in consul_endpoints and remove them
        # from fdb_endpoints

        delete_list = [tuple([tup[0]]) for tup in self.fdb_endpoints
                       if tup[0] not in [x[0] for x in
                       self.consul_endpoints]]
        if len(delete_list) > 0:
            print '\n--- To remove ---'
            for d in delete_list:
                print d[0]
        else:
            print 'Nothing to delete'

        if self.config['dry_run']:
            print 'This is a dry run, no modifications will be made to ' \
                + 'your system'
        elif len(replace_list) or len(delete_list):
            with Namespace(self.vxlan['filepath'], 'net'):
                for tup in replace_list:
                    o = subprocess.check_output([
                        'bridge', 'fdb',
                        'replace',
                        tup[0],
                        'dev',
                        self.vxlan['device'],
                        'dst',
                        tup[2],
                        ]).split('\n')
                    if o[0] != '':
                        print o
                for tup in delete_list:
                    o = subprocess.check_output([
                        'bridge',
                        'fdb',
                        'delete',
                        tup[0],
                        'dev',
                        self.vxlan['device'],
                        ]).split('\n')
                    if o[0] != '':
                        print o


def parse_args():
    parser = ArgumentParser()
    parser.add_argument(
        '-c',
        '--config',
        required=True,
        metavar='config_file',
        dest='config_file',
        help='YAML configuration file',
        )
    args = parser.parse_args()
    return args


def parse_config(config_file):
    with open(config_file) as f:
        config = yaml.load(f)
        return config


def main():
    args = parse_args()
    config = parse_config(args.config_file)
    v = VXLANFixer(**config)

    # print('--- Consul endpoints ---')
    # v.dump_consul_endpoints()

    # print('\n--- FDB endpoints ---')
    # v.dump_fdb_endpoints()

    print '--- Messy entries ---'
    v.find_messy_entries()


if __name__ == '__main__':
    main()
