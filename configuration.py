#!/usr/bin/env python3
# -*- coding: utf-8 -*-

""" This module defines the classes for the protocol handling.
"""
import random
import socket
from collections import namedtuple
from copy import deepcopy
from ipaddress import ip_address, ip_network

import xfrm
from message import PayloadID, Proposal, TrafficSelector, Transform

__author__ = 'Alejandro Perez-Mendez <alejandro.perez.mendez@gmail.com>'


class ConfigurationError(Exception):
    pass


class ConfigurationNotFound(ConfigurationError):
    pass


_encr_name_to_transform = {
    'aes128': Transform(Transform.Type.ENCR, Transform.EncrId.ENCR_AES_CBC, 128),
    'aes256': Transform(Transform.Type.ENCR, Transform.EncrId.ENCR_AES_CBC, 256),
}

_integ_name_to_transform = {
    'sha256': Transform(Transform.Type.INTEG, Transform.IntegId.AUTH_HMAC_SHA2_256_128),
    'sha512': Transform(Transform.Type.INTEG, Transform.IntegId.AUTH_HMAC_SHA2_512_256),
    'sha1': Transform(Transform.Type.INTEG, Transform.IntegId.AUTH_HMAC_SHA1_96),
}

_prf_name_to_transform = {
    'sha1': Transform(Transform.Type.PRF, Transform.PrfId.PRF_HMAC_SHA1),
    'sha256': Transform(Transform.Type.PRF, Transform.PrfId.PRF_HMAC_SHA2_256),
    'sha512': Transform(Transform.Type.PRF, Transform.PrfId.PRF_HMAC_SHA2_512),
}

_dh_name_to_transform = {
    '1': Transform(Transform.Type.DH, Transform.DhId.DH_1),
    '2': Transform(Transform.Type.DH, Transform.DhId.DH_2),
    '5': Transform(Transform.Type.DH, Transform.DhId.DH_5),
    '14': Transform(Transform.Type.DH, Transform.DhId.DH_14),
    '15': Transform(Transform.Type.DH, Transform.DhId.DH_15),
    '16': Transform(Transform.Type.DH, Transform.DhId.DH_16),
    '17': Transform(Transform.Type.DH, Transform.DhId.DH_17),
    '18': Transform(Transform.Type.DH, Transform.DhId.DH_18),
}

_ip_proto_name_to_enum = {
    'tcp': TrafficSelector.IpProtocol.TCP,
    'any': TrafficSelector.IpProtocol.ANY,
    'udp': TrafficSelector.IpProtocol.UDP,
    'icmp': TrafficSelector.IpProtocol.ICMP,
}

_mode_name_to_enum = {
    'transport': xfrm.Mode.TRANSPORT,
    'tunnel': xfrm.Mode.TUNNEL,
}

_ipsec_proto_name_to_enum = {
    'esp': Proposal.Protocol.ESP,
    'ah': Proposal.Protocol.AH,
}

IkeConfiguration = namedtuple('IkeConfiguration',
                              ['psk', 'lifetime', 'dpd', 'id', 'peer_id', 'encr', 'integ', 'prf', 'dh', 'protect'],
                              defaults=(None,)*10)
IpsecConfiguration = namedtuple('IpsecConfiguration',
                                ['my_subnet', 'index', 'peer_subnet', 'my_port', 'lifetime', 'peer_port', 'ip_proto',
                                 'mode', 'ipsec_proto', 'encr', 'integ'],
                                defaults=(None,)*11)


class Configuration(object):
    """ Represents the daemon configuration.
    """

    def __init__(self, my_addr, conf_dict):
        """ Creates a new Configuration object from a textual dict (e.g. coming from JSON or YAML)
        """
        self._configuration = {}
        for key, value in conf_dict.items():
            try:
                self.my_addr = self._load_ip_address(my_addr)
                ip = ip_address(socket.gethostbyname(key))
            except (ValueError, socket.gaierror) as ex:
                raise ConfigurationError(str(ex))
            self._configuration[ip] = self._load_ike_conf(ip, value)

    def items(self):
        return self._configuration.items()

    def _load_ike_conf(self, peer_ip, conf_dict):
        default_id = 'https://github.com/alejandro-perez/pyikev2'
        ipsec_confs = []
        for ipsec_conf in conf_dict.get('protect', [{}]):
            ipsec_confs.append(self._load_ipsec_conf(peer_ip, ipsec_conf))

        return IkeConfiguration(
            psk=conf_dict.get('psk', 'whatever').encode(),
            lifetime=int(conf_dict.get('lifetime', 15 * 60)),
            dpd=int(conf_dict.get('dpd', 60)),
            id=PayloadID(PayloadID.Type.ID_FQDN, conf_dict.get('id', default_id).encode()),
            peer_id=PayloadID(PayloadID.Type.ID_FQDN, conf_dict.get('peer_id', default_id).encode()),
            encr=self._load_crypto_algs('encr', conf_dict.get('encr', ['aes256']), _encr_name_to_transform),
            integ=self._load_crypto_algs('integ', conf_dict.get('integ', ['sha256']), _integ_name_to_transform),
            prf=self._load_crypto_algs('prf', conf_dict.get('prf', ['sha256']), _prf_name_to_transform),
            dh=self._load_crypto_algs('dh', conf_dict.get('dh', ['14']), _dh_name_to_transform),
            protect=ipsec_confs
        )

    @staticmethod
    def _load_ip_network(value):
        try:
            return ip_network(value)
        except ValueError as ex:
            raise ConfigurationError(str(ex))

    @staticmethod
    def _load_ip_address(value):
        try:
            return ip_address(value)
        except ValueError as ex:
            raise ConfigurationError(str(ex))

    def _load_ipsec_conf(self, peer_ip, conf_dict):
        return IpsecConfiguration(
            my_subnet=self._load_ip_network(conf_dict.get('my_subnet', self.my_addr)),
            index=int(conf_dict.get('index', random.randint(0, 2**20))),
            peer_subnet=self._load_ip_network(conf_dict.get('peer_subnet', peer_ip)),
            my_port=int(conf_dict.get('my_port', 0)),
            lifetime=int(conf_dict.get('lifetime', 5 * 60)),
            peer_port=int(conf_dict.get('peer_port', 0)),
            ip_proto=self._load_from_dict(conf_dict.get('ip_proto', 'any'), _ip_proto_name_to_enum),
            mode=self._load_from_dict(conf_dict.get('mode', 'transport'), _mode_name_to_enum),
            ipsec_proto=self._load_from_dict(conf_dict.get('ipsec_proto', 'esp'), _ipsec_proto_name_to_enum),
            encr=self._load_crypto_algs('encr', conf_dict.get('encr', ['aes256']), _encr_name_to_transform),
            integ=self._load_crypto_algs('integ', conf_dict.get('integ', ['sha256']), _integ_name_to_transform),
        )

    def get_ike_configuration(self, addr):
        addr = ip_address(addr)
        try:
            found = next(key for key in self._configuration if addr == key)
        except StopIteration:
            raise ConfigurationNotFound
        return self._configuration[found]

    @staticmethod
    def _load_from_dict(key, cnf_dict):
        try:
            return cnf_dict[key]
        except KeyError:
            raise ConfigurationError('{} not supported'.format(key))

    def _load_crypto_algs(self, key, names, name_to_transform):
        transforms = []
        if type(names) is not list:
            raise ConfigurationError('{} should be a list.'.format(key))
        for x in names:
            transform = self._load_from_dict(str(x), deepcopy(name_to_transform))
            transforms.append(transform)
        return transforms
