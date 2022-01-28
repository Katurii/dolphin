# Copyright 2022 The SODA Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http:#www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import datetime
import hashlib
import time

from oslo_log import log

from delfin import exception, utils
from delfin.common import constants
from delfin.drivers import driver
from delfin.drivers.pure.flasharray import rest_handler, consts
from delfin.i18n import _

LOG = log.getLogger(__name__)


class PureFlashArrayDriver(driver.StorageDriver):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.rest_handler = rest_handler.RestHandler(**kwargs)
        self.rest_handler.login()

    def list_volumes(self, context):
        list_volumes = []
        volumes = self.rest_handler.get_volumes()
        if volumes:
            for volume in volumes:
                volume_name = volume.get('name')
                total_capacity = int(volume.get('size',
                                                consts.DEFAULT_CAPACITY))
                used_capacity = int(volume.get('volumes',
                                               consts.DEFAULT_CAPACITY))
                volume_dict = {
                    'native_volume_id': volume_name,
                    'name': volume_name,
                    'total_capacity': total_capacity,
                    'used_capacity': used_capacity,
                    'free_capacity': total_capacity - used_capacity,
                    'storage_id': self.storage_id,
                    'status': constants.StorageStatus.NORMAL,
                    'type': constants.VolumeType.THIN if
                    volume.get('thin_provisioning') is not None
                    else constants.VolumeType.THICK
                }
                list_volumes.append(volume_dict)
        return list_volumes

    def add_trap_config(self, context, trap_config):
        pass

    def clear_alert(self, context, alert):
        pass

    def get_storage(self, context):
        storages = self.rest_handler.rest_call(
            self.rest_handler.REST_STORAGE_URL)
        total_capacity = None
        used_capacity = None
        if storages:
            for storage in storages:
                used_capacity = int(storage.get('total',
                                                consts.DEFAULT_CAPACITY))
                total_capacity = int(storage.get('capacity',
                                                 consts.DEFAULT_CAPACITY))
                break
        raw_capacity = consts.DEFAULT_CAPACITY
        disks = self.list_disks(context)
        if disks:
            for disk in disks:
                raw_capacity = raw_capacity + disk.get('capacity')
        arrays = self.rest_handler.rest_call(self.rest_handler.REST_ARRAY_URL)
        storage_name = None
        serial_number = None
        version = None
        if arrays:
            storage_name = arrays.get('array_name')
            serial_number = arrays.get('id')
            version = arrays.get('version')
        model = None
        status = constants.StorageStatus.NORMAL
        controllers = self.rest_handler.rest_call(
            self.rest_handler.REST_CONTROLLERS_URL)
        if controllers:
            for controller in controllers:
                if controller.get('mode') == consts.CONTROLLER_PRIMARY:
                    model = controller.get('model')
                    if controller.get('status') != \
                            consts.NORMAL_CONTROLLER_STATUS:
                        status = constants.StorageStatus.ABNORMAL
        if not all((storages, arrays, controllers)):
            LOG.error('get_storage error, Unable to obtain data.')
            raise exception.StorageBackendException('Unable to obtain data')
        storage_result = {
            'model': model,
            'total_capacity': total_capacity,
            'raw_capacity': raw_capacity,
            'used_capacity': used_capacity,
            'free_capacity': total_capacity - used_capacity,
            'vendor': 'PURE',
            'name': storage_name,
            'serial_number': serial_number,
            'firmware_version': version,
            'status': status
        }
        return storage_result

    def list_alerts(self, context, query_para=None):
        alerts = self.rest_handler.rest_call(self.rest_handler.REST_ALERTS_URL)
        alerts_list = []
        if alerts:
            for alert in alerts:
                alerts_model = dict()
                opened = alert.get('opened')
                time_difference = time.mktime(
                    time.localtime()) - time.mktime(time.gmtime())
                timestamp = (int(datetime.datetime.strptime
                                 (opened, '%Y-%m-%dT%H:%M:%SZ').timestamp()
                                 + time_difference) *
                             consts.DEFAULT_LIST_ALERTS_TIME_CONVERSION) if \
                    opened is not None else None
                if query_para is not None:
                    try:
                        if timestamp is None or timestamp \
                                < int(query_para.get('begin_time')) or \
                                timestamp > int(query_para.get('end_time')):
                            continue
                    except Exception as e:
                        LOG.error(e)
                alerts_model['occur_time'] = timestamp
                alerts_model['alert_id'] = alert.get('id')
                alerts_model['severity'] = consts.SEVERITY_MAP.get(
                    alert.get('current_severity'),
                    constants.Severity.NOT_SPECIFIED)
                alerts_model['category'] = constants.Category.FAULT
                component_name = alert.get('component_name')
                alerts_model['location'] = component_name
                alerts_model['type'] = constants.EventType.EQUIPMENT_ALARM
                alerts_model['resource_type'] = constants.DEFAULT_RESOURCE_TYPE
                event = alert.get('event')
                alerts_model['alert_name'] = event
                alerts_model['match_key'] = hashlib.md5(str(alert.get('id')).
                                                        encode()).hexdigest()
                alerts_model['description'] = '({}:{}): {}'. \
                    format(alert.get('component_type'), component_name, event)
                alerts_list.append(alerts_model)
        return alerts_list

    @staticmethod
    def parse_alert(context, alert):
        try:
            alert_model = dict()
            alert_model['alert_id'] = alert.get(consts.PARSE_ALERT_ALERT_ID)
            alert_model['severity'] = consts.PARSE_ALERT_SEVERITY_MAP.get(
                alert.get(consts.PARSE_ALERT_SEVERITY),
                constants.Severity.NOT_SPECIFIED)
            alert_model['category'] = constants.Category.FAULT
            alert_model['occur_time'] = utils.utcnow_ms()
            alert_model['description'] = '({}:{}): {}'.format(alert.get(
                consts.PARSE_ALERT_STORAGE_NAME),
                alert.get(consts.PARSE_ALERT_CONTROLLER_NAME),
                alert.get(consts.PARSE_ALERT_DESCRIPTION))
            alert_model['location'] = alert.get(
                consts.PARSE_ALERT_CONTROLLER_NAME)
            alert_model['type'] = constants.EventType.EQUIPMENT_ALARM
            alert_model['resource_type'] = constants.DEFAULT_RESOURCE_TYPE
            alert_model['alert_name'] = alert.get(
                consts.PARSE_ALERT_ALERT_NAME)
            alert_model['sequence_number'] = alert.get(
                consts.PARSE_ALERT_ALERT_ID)
            alert_model['match_key'] = hashlib.md5(str(alert.get(
                consts.PARSE_ALERT_ALERT_ID)).encode()).hexdigest()
            return alert_model
        except Exception as e:
            LOG.error(e)
            msg = (_("Failed to build alert model as some attributes missing"))
            raise exception.InvalidResults(msg)

    def list_controllers(self, context):
        list_controllers = []
        controllers = self.rest_handler.rest_call(
            self.rest_handler.REST_CONTROLLERS_URL)
        hardware = self.get_hardware()
        if controllers:
            for controller in controllers:
                controllers_dict = dict()
                controller_name = controller.get('name')
                controllers_dict['name'] = controller_name
                controllers_dict['status'] = consts.CONTROLLER_STATUS_MAP.get(
                    hardware.get(controller_name, {}).get('status'),
                    constants.ControllerStatus.UNKNOWN)
                controllers_dict['soft_version'] = controller.get('version')
                controllers_dict['storage_id'] = self.storage_id
                controllers_dict['native_controller_id'] = controller_name
                controllers_dict['location'] = controller_name
                list_controllers.append(controllers_dict)
        return list_controllers

    def list_disks(self, context):
        hardware_dict = self.get_hardware()
        list_disks = []
        disks = self.rest_handler.rest_call(self.rest_handler.REST_DISK_URL)
        if disks:
            for disk in disks:
                disk_type = disk.get('type')
                if disk_type == consts.DISK_TYPE_NVRAM or disk_type is None:
                    continue
                disk_dict = dict()
                drive_name = disk.get('name')
                disk_dict['name'] = drive_name
                physical_type = disk_type.lower() if disk_type is not None \
                    else None
                disk_dict['physical_type'] = physical_type \
                    if physical_type in constants.DiskPhysicalType.ALL else \
                    constants.DiskPhysicalType.UNKNOWN
                disk_dict['status'] = consts.DISK_STATUS_MAP. \
                    get(disk.get('status'), constants.DiskStatus.OFFLINE)
                disk_dict['storage_id'] = self.storage_id
                disk_dict['capacity'] = int(disk.get('capacity',
                                                     consts.DEFAULT_CAPACITY))
                hardware_object = hardware_dict.get(drive_name, {})
                speed = hardware_object.get('speed')
                disk_dict['speed'] = int(speed) if speed is not None else None
                disk_dict['model'] = hardware_object.get('model')
                disk_dict['serial_number'] = hardware_object. \
                    get('serial_number')
                disk_dict['native_disk_id'] = drive_name
                disk_dict['location'] = drive_name
                disk_dict['manufacturer'] = "PURE"
                disk_dict['firmware'] = ""
                list_disks.append(disk_dict)
        return list_disks

    def get_hardware(self):
        hardware_dict = dict()
        hardware = self.rest_handler.rest_call(
            self.rest_handler.REST_HARDWARE_URL)
        if hardware:
            for hardware_value in hardware:
                hardware_map = dict()
                hardware_map['speed'] = hardware_value.get('speed')
                hardware_map['serial_number'] = hardware_value.get('serial')
                hardware_map['model'] = hardware_value.get('model')
                hardware_map['status'] = hardware_value.get('status')
                hardware_dict[hardware_value.get('name')] = hardware_map
        return hardware_dict

    def list_ports(self, context):
        list_ports = []
        networks = self.get_network()
        ports = self.get_ports()
        hardware_dict = self.rest_handler.rest_call(
            self.rest_handler.REST_HARDWARE_URL)
        if not hardware_dict:
            return list_ports
        for hardware in hardware_dict:
            hardware_result = dict()
            hardware_name = hardware.get('name')
            if 'FC' in hardware_name:
                hardware_result['type'] = constants.PortType.FC
            elif 'ETH' in hardware_name:
                hardware_result['type'] = constants.PortType.ETH
            elif 'SAS' in hardware_name:
                hardware_result['type'] = constants.PortType.SAS
            else:
                continue
            hardware_result['name'] = hardware_name
            hardware_result['native_port_id'] = hardware_name
            hardware_result['storage_id'] = self.storage_id
            hardware_result['location'] = hardware_name
            speed = hardware.get('speed')
            if speed is None:
                hardware_result['connection_status'] = \
                    constants.PortConnectionStatus.UNKNOWN
            elif speed == consts.CONSTANT_ZERO:
                hardware_result['connection_status'] = \
                    constants.PortConnectionStatus.DISCONNECTED
                hardware_result['speed'] = speed
            else:
                hardware_result['connection_status'] = \
                    constants.PortConnectionStatus.CONNECTED
                hardware_result['speed'] = int(speed)
            hardware_result['health_status'] = consts.PORT_STATUS_MAP.get(
                hardware.get('status'), constants.PortHealthStatus.UNKNOWN)
            port = ports.get(hardware_name)
            if port:
                hardware_result['wwn'] = port.get('wwn')
            network = networks.get(hardware_name)
            if network:
                hardware_result['mac_address'] = network.get('mac_address')
                hardware_result['logical_type'] = network.get('logical_type')
                hardware_result['ipv4_mask'] = network.get('ipv4_mask')
                hardware_result['ipv4'] = network.get('ipv4')
            list_ports.append(hardware_result)
        return list_ports

    def get_network(self):
        networks_object = dict()
        networks = self.rest_handler.rest_call(
            self.rest_handler.REST_NETWORK_URL)
        if networks:
            for network in networks:
                network_dict = dict()
                network_dict['mac_address'] = network.get('hwaddr')
                services_list = network.get('services')
                if services_list:
                    for services in services_list:
                        network_dict['logical_type'] = services if \
                            services in constants.PortLogicalType.ALL else None
                        break
                network_dict['ipv4_mask'] = network.get('netmask')
                network_dict['ipv4'] = network.get('address')
                network_name = network.get('name').upper()
                networks_object[network_name] = network_dict
        return networks_object

    def get_ports(self):
        ports_dict = dict()
        ports = self.rest_handler.rest_call(self.rest_handler.REST_PORT_URL)
        if ports:
            for port in ports:
                port_dict = dict()
                port_name = port.get('name')
                wwn = port.get('wwn')
                port_dict['wwn'] = self.get_splice_wwn(wwn) \
                    if wwn is not None else port.get('iqn')
                ports_dict[port_name] = port_dict
        return ports_dict

    @staticmethod
    def get_splice_wwn(wwn):
        wwn_list = list(wwn)
        wwn_splice = wwn_list[0]
        for serial in range(1, len(wwn_list)):
            if serial % consts.SPLICE_WWN_SERIAL == consts.CONSTANT_ZERO:
                wwn_splice = '{}{}'.format(wwn_splice, consts.SPLICE_WWN_COLON)
            wwn_splice = '{}{}'.format(wwn_splice, wwn_list[serial])
        return wwn_splice

    def list_storage_pools(self, context):
        return []

    def remove_trap_config(self, context, trap_config):
        pass

    def reset_connection(self, context, **kwargs):
        self.rest_handler.logout()
        self.rest_handler.login()

    @staticmethod
    def get_access_url():
        return 'https://{ip}'

    def list_storage_host_initiators(self, context):
        list_initiators = []
        initiators = self.rest_handler.rest_call(
            self.rest_handler.REST_HOST_URL)
        for initiator in (initiators or []):
            host_id = initiator.get('name')
            self.get_initiator(initiator, list_initiators, host_id, 'iqn',
                               constants.InitiatorType.ISCSI)
            self.get_initiator(initiator, list_initiators, host_id, 'wwn',
                               constants.InitiatorType.FC)
            self.get_initiator(initiator, list_initiators, host_id, 'nqn',
                               constants.InitiatorType.NVME_OVER_FABRIC)
        return list_initiators

    def get_initiator(self, initiator, list_initiators, host_id, protocol,
                      network):
        protocol_list = initiator.get(protocol)
        if protocol_list:
            for initiator_protocol in (protocol_list or []):
                if 'wwn' in protocol:
                    initiator_protocol = self.get_splice_wwn(
                        initiator_protocol)
                initiator_d = {
                    'native_storage_host_initiator_id': initiator_protocol,
                    'native_storage_host_id': host_id,
                    'name': initiator_protocol,
                    'type': network,
                    'status': constants.InitiatorStatus.UNKNOWN,
                    'wwn': initiator_protocol,
                    'storage_id': self.storage_id
                }
                list_initiators.append(initiator_d)

    def list_storage_hosts(self, ctx):
        host_list = []
        hosts = self.rest_handler.rest_call(
            self.rest_handler.REST_HOST_PERSONALITY_URL)
        for host in (hosts or []):
            name = host.get('name')
            personality = host.get('personality')
            if personality:
                personality = personality.lower()
            h = {
                "name": name,
                "storage_id": self.storage_id,
                "native_storage_host_id": name,
                "os_type": consts.HOST_OS_TYPES_MAP.get(
                    personality, constants.HostOSTypes.UNKNOWN),
                "status": constants.HostStatus.NORMAL
            }
            host_list.append(h)
        return host_list

    def list_storage_host_groups(self, context):
        host_groups = self.rest_handler.rest_call(
            self.rest_handler.REST_HGROUP_URL)
        host_group_list = []
        storage_host_grp_relation_list = []
        for hgroup in (host_groups or []):
            name = hgroup.get('name')
            hg = {
                'native_storage_host_group_id': name,
                'name': name,
                'storage_id': self.storage_id
            }
            host_group_list.append(hg)
            for host in (hgroup.get('hosts') or []):
                host_relation = {
                    'native_storage_host_group_id': name,
                    'storage_id': self.storage_id,
                    'native_storage_host_id': host
                }
                storage_host_grp_relation_list.append(host_relation)
        result = {
            'storage_host_groups': host_group_list,
            'storage_host_grp_host_rels': storage_host_grp_relation_list
        }
        return result

    def list_volume_groups(self, context):
        volume_groups = self.rest_handler.rest_call(
            self.rest_handler.REST_VOLUME_GROUP_URL)
        vol_group_list = []
        vol_grp_vol_relation_list = []
        for volume_group in (volume_groups or []):
            name = volume_group.get('name')
            vol_g = {
                'name': name,
                'storage_id': self.storage_id,
                'native_volume_group_id': name
            }
            vol_group_list.append(vol_g)
            for volume_id in (volume_group.get('volumes') or []):
                volume_group_relation = {
                    'storage_id': self.storage_id,
                    'native_volume_group_id': name,
                    'native_volume_id': volume_id
                }
                vol_grp_vol_relation_list.append(volume_group_relation)
        result = {
            'volume_groups': vol_group_list,
            'vol_grp_vol_rels': vol_grp_vol_relation_list
        }
        return result

    def list_masking_views(self, context):
        list_masking_views = []
        masking_views = self.rest_handler.rest_call(
            self.rest_handler.REST_HOST_ALL_URL)
        view_id_dict = {}
        for masking_view in (masking_views or []):
            hgroup = masking_view.get('hgroup')
            host_id = masking_view.get('name')
            native_volume_id = masking_view.get('vol')
            native_masking_view_id = '{}{}{}'.format(
                host_id, hgroup, native_volume_id)
            if view_id_dict.get(native_masking_view_id):
                continue
            view_id_dict[native_masking_view_id] = native_masking_view_id
            view = {
                'native_masking_view_id': native_masking_view_id,
                'name': native_masking_view_id,
                'native_storage_host_group_id': hgroup if hgroup else None,
                'native_storage_host_id': None if hgroup else host_id,
                'native_volume_id': native_volume_id,
                'storage_id': self.storage_id
            }
            list_masking_views.append(view)
        return list_masking_views

    def get_volume_group(self):
        volume_g = {}
        volume_groups = self.rest_handler.rest_call(
            self.rest_handler.REST_VOLUME_GROUP_URL)
        for volume_group in (volume_groups or []):
            name = volume_group.get('name')
            for volume_id in (volume_group.get('volumes') or []):
                volume_g[volume_id] = name
        return volume_g
